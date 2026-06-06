# LLM Pipeline Architecture Analysis & Optimization Plan
**Botamin BI — Voice AI Analytics Platform**

**Date:** 2026-06-06  
**Author:** Senior Architect Review  
**Status:** Strategic Recommendations

---

## Executive Summary

Current LLM integration in Botamin BI follows a **single-call-per-dialogue** pattern that creates significant token overhead and misses opportunities for aggregated insights. This document outlines a comprehensive optimization strategy that:

1. **Reduces token consumption by ~40-60%** through intelligent batching
2. **Enables cross-call pattern discovery** not possible with per-call analysis
3. **Introduces dynamic threshold optimization** via LLM feedback loops
4. **Creates a unified analytics framework** for metrics, custdev, and quality scoring

**Estimated Impact:** 50-70% reduction in LLM costs while gaining new analytical capabilities.

---

## Current Architecture Analysis

### 1. Data Flow (Current State)

```
┌─────────────────┐
│  Raw CSV/Data   │
└────────┬────────┘
         │
         ▼
┌─────────────────┐     ┌──────────────────┐
│  Ingest Module  │────▶│  Deterministic   │
└────────┬────────┘     │  Classifier      │
         │              └──────────────────┘
         ▼                       │
┌─────────────────┐               │
│  Features       │◀──────────────┘
│  Extraction     │
└────────┬────────┘
         │
         ▼
┌─────────────────┐     ┌──────────────────┐
│  LLM Analysis   │────▶│  Per-Call JSON    │
│  (per call)     │     │  (via cache key)  │
└────────┬────────┘     └──────────────────┘
         │
         ▼
┌─────────────────┐
│  Metrics &      │
│  Diagnostics    │
└─────────────────┘
```

### 2. Identified Problems

#### Problem 1: Token Overhead (Per-Call System Prompt)
Each of ~2,000 calls sends the full system prompt (~1,200 tokens):
- **Current:** 2,000 calls × 1,200 tokens = 2.4M tokens overhead
- **With batching:** ~50 batches × 1,200 tokens = 60K tokens overhead
- **Savings:** ~97.5% reduction in system prompt tokens

#### Problem 2: No Cross-Call Pattern Recognition
Each call is analyzed in isolation, missing:
- **Temporal patterns:** "Monday mornings have 2.3× more ASR failures"
- **Sequential patterns:** "Clients who object on price after 45s never convert"
- **Clustering:** "There are 3 distinct failure modes we should address separately"

#### Problem 3: Static Thresholds
Current thresholds (`MIN_CLIENT_TURNS=3`, etc.) are hard-coded:
- No feedback loop from actual performance
- Cannot adapt to changing call patterns
- No A/B testing framework

#### Problem 4: CustDev Disabled by Default
The custdev module falls back to keyword matching because:
- Per-call LLM analysis is too expensive for full dataset
- No dedicated "research LLM pass" separate from operational analysis

---

## Proposed Architecture

### 1. Three-Tier LLM Strategy

```
                    ┌─────────────────────────────────────┐
                    │         LLM Orchestrator             │
                    └──────────────────┬──────────────────┘
                                       │
              ┌────────────────────────┼────────────────────────┐
              │                        │                        │
              ▼                        ▼                        ▼
    ┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
    │  Tier 1:        │     │  Tier 2:          │     │  Tier 3:        │
    │  Batch Analysis │     │  Per-Call        │     │  Research       │
    │  (40-50 calls)  │────▶│  Deep Dive       │────▶│  Aggregated     │
    │                 │     │  (flagged only)  │     │  Insights       │
    └─────────────────┘     └──────────────────┘     └─────────────────┘
              │                        │                        │
              ▼                        ▼                        ▼
    ┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
    │  Rapid Screen   │     │  Detailed JSON    │     │  CustDev         │
    │  Stage/Evidence │     │  with quotes      │     │  Themes          │
    │  Patterns       │     │  Voice metrics    │     │  Hypotheses      │
    └─────────────────┘     └──────────────────┘     └─────────────────┘
```

### 2. Data Packing Format

#### Optimized JSON Structure (Minimal Overhead)

```json
{
  "v": 1,
  "calls": [
    {
      "i": "c_01048",
      "d": 45.2,
      "t": [
        {"r": "b", "txt": "Алекса́ндр..."},
        {"r": "c", "txt": "Слушаю..."},
        {"r": "b", "txt": "Мы предлагаем..."}
      ]
    }
  ]
}
```

**Key Design Decisions:**
- **Short keys:** `i` instead of `id`, `r` instead of `role`, `txt` instead of `text`
- **Array format:** Faster parsing than newline-separated text
- **Versioning:** `v` field allows schema evolution
- **No metadata in batch:** Only in per-call deep dive

#### Token Efficiency Comparison

| Format | Tokens per 50-call batch | Overhead |
|--------|--------------------------|----------|
| Current (separate calls) | ~60,000 (1,200 × 50) | 1,200 per call |
| New (batch) | ~18,000 | ~360 per batch |
| **Savings** | **70%** | **97%** |

### 3. Tier 1: Batch Rapid Analysis

**Purpose:** Screen 40-50 calls for:
- Stage classification (S0-S4)
- Pattern detection (PSY-*)
- Objection type detection
- Flagging for Tier 2 deep dive

**System Prompt (Batch Mode):**
```
Ты — старший аналитик голосовых диалогов. 
АНАЛИЗИРУЙ [40-50] звонков в БАТЧЕ.

Для каждого верни JSON:
{
  "id": "c_XXXXX",
  "stage": 0-4,
  "patterns": ["PSY-XXX", ...],
  "objections": ["price", ...],
  "flag": boolean  // true = нужна Tier 2 детализация
}
```

**Performance Characteristics:**
- Input: ~15K tokens (50 calls × ~300 tokens avg)
- Output: ~500 tokens (50 × 10 tokens)
- Latency: 3-5 seconds
- Cost: ~80% lower than per-call analysis

### 4. Tier 2: Targeted Deep Dive

**Purpose:** Detailed analysis of flagged calls only (~10-20% of total)

**Trigger Conditions (configurable):**
- `stage == 3` (meeting agreed) — celebrate success
- `stage == 2` AND `objections present` — why no close?
- `patterns contains PSY-094 or PSY-201` — bot failure
- `quality_score < 0.3` — poor performance
- Random 5% sample of S0-S1 calls

**Full Analysis Output:**
```json
{
  "id": "c_01048",
  "furthest_stage": 3,
  "stage_evidence": {...},
  "objections": [...],
  "bot_patterns": [...],
  "voice": {...},
  "quality_score": 0.72,
  "loss_reason": "...",
  "summary": "...",
  "quotes": {
    "consent": "...",
    "objection": "...",
    "pattern": "..."
  }
}
```

### 5. Tier 3: Aggregated Research

**Purpose:** Cross-call insights that emerge only from aggregated analysis

**Queries:**
1. **Temporal Analysis:** "Group calls by hour. What patterns emerge?"
2. **Failure Clustering:** "Identify 3-5 distinct failure modes with their characteristics."
3. **Conversion Signals:** "What combinations of factors predict meeting agreement?"
4. **CustDev Extraction:** "What pain points and wishes do clients express?"

**Input:** Aggregated statistics + flagged call transcripts
**Output:** Research-grade insights for product and prompt improvement

---

## Dynamic Threshold Optimization

### 1. LLM-as-Optimizer Pattern

```python
# Current: static thresholds
MIN_CLIENT_TURNS = 3

# Proposed: LLM-optimized thresholds
thresholds = {
    "min_client_turns": 3.0,
    "substantive_word_count": 2.0,
    "repair_failure_threshold": 2,
    "long_monologue_words": 60,
    "quality_score_warning": 0.4
}

# Weekly optimization
def optimize_thresholds(current_metrics, recent_calls):
    prompt = f"""
    Current metrics: {current_metrics}
    Recent 1000 calls summary: {...}
    
    Our thresholds control classification sensitivity. Too strict = miss insights.
    Too loose = noise. Recommend threshold adjustments to:
    1. Increase precision (reduce false positives)
    2. Maintain recall (catch real issues)
    
    Return JSON with rationale.
    """
    
    return llm.call(prompt)
```

### 2. Feedback Loop Architecture

```
┌──────────────────┐
│ Current Metrics  │
└────────┬─────────┘
         │
         ▼
┌──────────────────┐     ┌──────────────────┐
│ LLM Threshold    │────▶│  A/B Test         │
│ Optimizer         │     │  Framework        │
└────────┬─────────┘     └──────────────────┘
         │                        │
         ▼                        ▼
┌──────────────────┐     ┌──────────────────┐
│ Updated Config   │────▶│  Validation       │
└──────────────────┘     └──────────────────┘
```

### 3. Configuration File (New Format)

```yaml
# config/thresholds.yaml
version: 1
last_optimized: "2026-06-06T00:00:00Z"
optimization_frequency: weekly

classification:
  min_client_turns:
    value: 3
    min: 2
    max: 5
    llm_suggested: 3
    rationale: "Balances noise vs missed conversations"
    
  substantive_word_count:
    value: 2
    min: 1
    max: 4
    llm_suggested: 2
    
quality:
  warning_threshold:
    value: 0.4
    min: 0.2
    max: 0.6
    
batch_size:
  value: 50
  min: 20
  max: 100
  rationale: "Optimal for token efficiency vs latency"
```

---

## Implementation Roadmap

### Phase 1: Core Batch Engine (Week 1-2)

**File Structure:**
```
pipeline/
├── llm/
│   ├── __init__.py
│   ├── client.py          # Existing
│   ├── analyze.py         # Existing
│   ├── batch.py           # NEW: Batch orchestrator
│   ├── research.py        # NEW: Aggregated analysis
│   ├── optimizer.py       # NEW: Threshold optimization
│   └── schemas.py         # NEW: Shared JSON schemas
```

**Key Classes:**
```python
class BatchAnalyzer:
    """Process 40-50 calls in single LLM request"""
    def pack_calls(calls: List[Dict]) -> str
    def unpack_response(json_str: str) -> List[Dict]
    async def analyze_batch(calls) -> List[Dict]

class ResearchAnalyzer:
    """Cross-call pattern discovery"""
    async def temporal_analysis(calls) -> Dict
    async def failure_clustering(calls) -> List[Cluster]
    async def conversion_signals(calls) -> Dict

class ThresholdOptimizer:
    """LLM-driven threshold tuning"""
    async def suggest_adjustments(metrics) -> Dict
    async def validate_proposal(config) -> bool
```

### Phase 2: Integration (Week 3)

**Modified Pipeline:**
```python
# build.py modifications
async def run_pipeline_with_llm_tiers():
    # ... existing ingest ...
    
    # NEW: Tier 1 batch analysis
    batcher = BatchAnalyzer(get_client())
    batches = chunk_calls(features, size=50)
    tier1_results = await batcher.analyze_all(batches)
    
    # NEW: Tier 2 targeted deep dive
    flagged = [c for c in tier1_results if c.get("flag")]
    tier2_results = await analyze_detailed(flagged)
    
    # NEW: Tier 3 research
    research = await ResearchAnalyzer(get_client()).analyze_all(features)
    
    # Merge and proceed
    merged = merge_results(tier1_results, tier2_results)
    # ... metrics computation ...
```

### Phase 3: Dynamic Thresholds (Week 4)

**Configuration:**
- Add `config/thresholds.yaml`
- Add `--optimize-thresholds` CLI flag
- Create threshold validation framework

### Phase 4: Dashboard Integration (Week 5)

**New Pages:**
1. `/research` — Aggregated insights from Tier 3
2. `/thresholds` — View and adjust thresholds with LLM suggestions
3. `/compare` — A/B test results for threshold changes

---

## Token Cost Analysis

### Current (Per-Call Mode)
```
2,000 calls ×:
  - System prompt: 1,200 tokens
  - User message: 300 tokens (avg transcript)
  - Output: 200 tokens (JSON response)
  ─────────────────────────────────────
  Total: 1,700 tokens/call × 2,000 = 3.4M tokens
```

### Proposed (Three-Tier)
```
Tier 1 - Batch Screening (2,000 calls in 40 batches):
  - System: 1,200 tokens × 40 = 48,000
  - Input: 15,000 tokens × 40 = 600,000
  - Output: 500 tokens × 40 = 20,000
  ─────────────────────────────────────
  Subtotal: 668,000 tokens

Tier 2 - Deep Dive (20% of calls = 400 calls):
  - System: 1,200 tokens × 400 = 480,000
  - Input: 300 tokens × 400 = 120,000
  - Output: 200 tokens × 400 = 80,000
  ─────────────────────────────────────
  Subtotal: 680,000 tokens

Tier 3 - Research (5 aggregated queries):
  - System + Stats: 50,000 tokens × 5 = 250,000
  - Output: 2,000 tokens × 5 = 10,000
  ─────────────────────────────────────
  Subtotal: 260,000 tokens

────────────────────────────────────────────
TOTAL: 1,608,000 tokens
```

**Savings: 3.4M → 1.6M = 53% reduction**
**Gains: Cross-call insights, dynamic optimization**

---

## Risk Mitigation

### 1. Consistency with Deterministic Failsafe

**Strategy:** Run LLM and deterministic in parallel for validation period
```python
# Validation mode
dual_results = []
for call in calls:
    det = classify_dialogue(call)
    llm = llm_classify(call)
    dual_results.append({
        "call_id": call.id,
        "deterministic": det,
        "llm": llm,
        "agreement": compare(det, llm)
    })
```

### 2. Graceful Degradation

```python
try:
    tier1 = await batch_analyzer.analyze(batches)
except LLMError:
    logger.warning("LLM failed, falling back to deterministic")
    tier1 = deterministic_batch_classify(batches)
```

### 3. Cache Invalidation Strategy

```python
# Cache key includes:
# - Model version
# - System prompt hash
# - Schema version
# - Threshold config hash

def cache_key(transcript, config_hash):
    h = hashlib.sha256()
    h.update(transcript.encode())
    h.update(config_hash.encode())
    h.update(CURRENT_SCHEMA_VERSION.encode())
    return h.hexdigest()[:24]
```

---

## Success Metrics

### Technical Metrics
- [ ] Token reduction > 50%
- [ ] Batch analysis latency < 10 seconds per 50 calls
- [ ] Cache hit rate > 80% for re-runs
- [ ] LLM availability > 99.5% (with fallback)

### Business Metrics
- [ ] New insights discovered per week (Tier 3 output)
- [ ] Threshold optimization validated and applied
- [ ] CustDev coverage increased from keyword-only to LLM-enhanced
- [ ] A/B testing framework operational

---

## Next Steps

1. **Review & Approval** — Stakeholder sign-off on architecture
2. **Prototyping** — Implement BatchAnalyzer with 100-call test
3. **Measurement** — Run comparison test (current vs batch)
4. **Iterate** — Refine prompts based on validation results
5. **Rollout** — Phased deployment with feature flags

---

## Appendix: Example Prompts

### A. Batch Analysis Prompt (Tier 1)

```python
BATCH_SYSTEM_PROMPT = """
Ты — senior-аналитик диалогов AI-агента продаж.
АНАЛИЗИРУЙ [40-50] звонков ОДНИМ JSON-массивом.

Формат ввода:
{
  "v": 1,
  "calls": [
    {"i": "c_01048", "d": 45.2, "t": [{"r": "b", "txt": "..."}, ...]},
    ...
  ]
}

Правила:
1. Стадия (stage) засчитывается ТОЛЬКО по словам КЛИЕНТА.
2. Паттерны (PSY-*) выбирай из таксономии.
3. Возражения (objections) — по type.

Верни JSON-массив:
[
  {
    "i": "c_01048",
    "stage": 0-4,
    "patterns": ["PSY-XXX", ...],
    "objections": ["price", ...],
    "flag": true/false,
    "r": float  // 0-1 confidence
  }
]

flag=true если:
- stage == 3 (встреча) — celebrate
- stage == 2 AND objections — why no close?
- patterns contain PSY-094/PSY-201 — bot failure
- quality < 0.3 — poor performance
"""
```

### B. Research Prompt (Tier 3)

```python
RESEARCH_TEMPORAL_PROMPT = """
Ты — продуктовый аналитик голосового AI-агента.

ДАННЫЕ:
- 2000 звонков за период {date_range}
- Метрики по часам: {hourly_metrics}
- Выборка 100 звонков: {sample_transcripts}

ЗАДАЧА:
Найди временные паттерны, влияющие на качество диалогов.

Верни JSON:
{
  "patterns": [
    {
      "time_window": "9:00-11:00",
      "characteristics": "...",
      "metrics_diff": {...},
      "recommendation": "..."
    }
  ],
  "hypotheses": [...]
}
"""
```

### C. Threshold Optimizer Prompt

```python
OPTIMIZER_PROMPT = """
Ты — expert по машинному обучению и аналитике продуктов.

ТЕКУЩАЯ СИТУАЦИЯ:
- Метрики: {current_metrics}
- Thresholds: {current_thresholds}
- Проблема: {problem_description}

ЦЕЛЬ:
Предложи корректировку threshold'ов для улучшения [precision/recall].

Верни JSON:
{
  "suggestions": [
    {
      "threshold": "min_client_turns",
      "current": 3,
      "suggested": 4,
      "expected_impact": "...",
      "risk": "..."
    }
  ],
  "validation_plan": "..."
}
"""
```

---

*Document Version: 1.0*
*Last Updated: 2026-06-06*
