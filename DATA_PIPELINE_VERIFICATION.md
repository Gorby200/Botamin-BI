# Data Pipeline Verification — Botamin BI
**Complete Data Flow Analysis**
**2026-06-06**

---

## Executive Summary

Verified complete data pipeline from CSV ingestion to frontend analytics. Found and documented data flow, identified gaps in LLM tier integration and research result persistence.

---

## Data Flow Diagram

```
┌─────────────────────────────────────────────────────────────────────────┐
│                              DATA SOURCES                                │
├─────────────────────────────────────────────────────────────────────────┤
│  1. Google Sheets (via URL)                                            │
│  2. Local CSV/XLSX files                                               │
│     Columns: телефон, дата, длительность, статус, аудио,             │
│               причина завершения, история диалога                      │
└────────────────────────────────────┬────────────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                          INGEST LAYER                                   │
├─────────────────────────────────────────────────────────────────────────┤
│  Module: pipeline/ingest.py                                            │
│  Functions:                                                             │
│    - ingest_sheet(sheet_url, gid) → pd.DataFrame                      │
│    - ingest_file(file_path) → pd.DataFrame                             │
│                                                                         │
│  Output: DataFrame with raw columns                                    │
│  Cache: data/raw.csv                                                   │
└────────────────────────────────────┬────────────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                        PROFILING LAYER                                  │
├─────────────────────────────────────────────────────────────────────────┤
│  Module: pipeline/profile.py                                           │
│  Functions:                                                             │
│    - profile_data(df) → Profile                                         │
│                                                                         │
│  Statistics: total_rows, date_range, anomalies                         │
└────────────────────────────────────┬────────────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                     DETERMINISTIC CLASSIFIER                            │
│                         (FAILSAFE)                                      │
├─────────────────────────────────────────────────────────────────────────┤
│  Module: pipeline/stages.py                                             │
│  Function: classify_dialogue(...) → dict                               │
│                                                                         │
│  Input: dialogue text, status, end_reason, duration                     │
│  Output: {connected, furthest_stage, outcome, objections, patterns,     │
│           voice, quality_score, loss_reason, loss_layer, summary}      │
│                                                                         │
│  ALWAYS RUNS — even if LLM configured                                   │
└────────────────────────────────────┬────────────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                      LLM TIER 1: BATCH SCREENING                        │
│                      (IF CONFIGURED)                                    │
├─────────────────────────────────────────────────────────────────────────┤
│  Module: pipeline/llm/batch.py                                          │
│  Function: BatchAnalyzer.analyze_batch(180 calls)                      │
│                                                                         │
│  Input: 180 calls packed in minimal JSON                                │
│  Output: {call_id: {stage, patterns, objections, flag, confidence}}     │
│                                                                         │
│  replaces deterministic results where available                        │
│  flags calls for Tier 2 deep dive                                      │
└────────────────────────────────────┬────────────────────────────────────┘
                                     │
                    ┌────────────────┴────────────────┐
                    │                                 │
                    ▼                                 ▼
┌───────────────────────────┐         ┌───────────────────────────┐
│   LLM TIER 2: DEEP DIVE   │         │   DETERMINISTIC ONLY      │
│   (FLAGGED CALLS ONLY)     │         │   (NO LLM)                │
├───────────────────────────┤         ├───────────────────────────┤
│ Module: llm/analyze.py    │         │ Uses stage.py results     │
│ Function: run_analysis()  │         │                           │
│                           │         │                           │
│ Input: flagged calls      │         │                           │
│ Output: detailed JSON     │         │                           │
│ with quotes/evidence      │         │                           │
└───────────┬───────────────┘         └───────────┬───────────────┘
            │                                     │
            └──────────────────┬──────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                    METRICS COMPUTATION LAYER                            │
├─────────────────────────────────────────────────────────────────────────┤
│  Module: pipeline/metrics.py                                            │
│  Functions:                                                             │
│    - compute_metrics(df) → {reach, nsm, funnel, drivers, ...}          │
│    - Uses flattened analysis from LLM or deterministic                 │
│                                                                         │
│  Output: Complete metric tree with all KPIs                            │
└────────────────────────────────────┬────────────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                  DIAGNOSTICS & BACKLOG GENERATION                       │
├─────────────────────────────────────────────────────────────────────────┤
│  Module: pipeline/diagnostics.py                                       │
│  Functions:                                                             │
│    - audit_bot_patterns(df) → pattern audit                            │
│    - cluster_objections(df) → objection clusters                       │
│    - generate_backlog(...) → ranked hypotheses                         │
│                                                                         │
│  Module: pipeline/custdev.py                                           │
│  Function: build_custdev(df, features) → custdev insights              │
└────────────────────────────────────┬────────────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│              LLM TIER 3: RESEARCH (IF ENABLED)                          │
│              ⚠️  NOT FULLY INTEGRATED YET                              │
├─────────────────────────────────────────────────────────────────────────┤
│  Module: pipeline/llm/research.py                                       │
│  Functions:                                                             │
│    - temporal_analysis(calls_by_hour) → patterns                       │
│    - failure_clustering(failed_calls) → clusters                       │
│    - conversion_signals(all_calls) → signals                           │
│    - custdev_extraction(calls) → insights                              │
│                                                                         │
│  ⚠️  ISSUE: Results calculated but NOT written to JSON output         │
└────────────────────────────────────┬────────────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                       JSON OUTPUT LAYER                                 │
├─────────────────────────────────────────────────────────────────────────┤
│  Module: pipeline/build.py (_write_outputs)                            │
│                                                                         │
│  Files written to frontend/public/data/:                                │
│    1. dashboard.json — metrics, funnel, drivers, diagnostics           │
│    2. backlog.json — ranked hypotheses                                 │
│    3. custdev.json — customer insights                                  │
│    4. calls/index.json — call index                                    │
│    5. calls/c_XXXXX.json — individual call cards                        │
│                                                                         │
│  ⚠️  MISSING: research.json (Tier 3 results)                           │
└────────────────────────────────────┬────────────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                        FRONTEND CONSUMPTION                             │
├─────────────────────────────────────────────────────────────────────────┤
│  Module: frontend/src/hooks.ts                                          │
│  Functions:                                                             │
│    - useDashboard() → loads dashboard.json                              │
│    - useBacklog() → loads backlog.json                                  │
│    - useCustdev() → loads custdev.json                                 │
│    - useCalls() → loads calls/index.json + individual cards            │
│                                                                         │
│  Pages: Overview, Funnel, Diagnostics, Backlog, Calls, Methodology     │
│                                                                         │
│  ⚠️  NO /research page yet — Tier 3 insights not displayed             │
└─────────────────────────────────────────────────────────────────────────┘

---

## Critical Findings

### ❌ Issues Found

1. **Tier 3 Results Not Persisted**
   - Location: `pipeline/build.py:_write_outputs()`
   - Issue: `research_results` calculated but not written to JSON
   - Impact: Temporal patterns, failure clusters, conversion signals lost

2. **No /research Frontend Route**
   - Location: `frontend/src/App.tsx`
   - Issue: No page to display Tier 3 insights
   - Impact: Valuable cross-call patterns not visible to users

3. **LLM Status Incomplete**
   - Location: `dashboard.json meta.llm`
   - Issue: Missing tier1_analyzed, tier2_analyzed, tier3_run counts
   - Impact: Can't track LLM usage effectiveness

4. **Research Results Not in CustDev**
   - Location: `pipeline/custdev.py`
   - Issue: CustDev uses keyword matching, ignores LLM research insights
   - Impact: Rich customer insights not integrated

### ✅ What Works Correctly

1. **Ingest → Profile → Classification** ✓
2. **LLM Tier 1 Batch Processing** ✓
3. **LLM Tier 2 Deep Dive Integration** ✓
4. **Metrics Computation** ✓
5. **JSON Output for Dashboard** ✓
6. **Frontend Data Loading** ✓

---

## Required Fixes

### Fix 1: Persist Tier 3 Results

**File:** `pipeline/build.py:_write_outputs()`

```python
# After line 333, add:
if research_results:
    _write_json(out_dir / "research.json", research_results)
    logger.info("  Wrote research.json with Tier 3 insights")
```

### Fix 2: Add Research to Dashboard Meta

**File:** `pipeline/build.py:_write_outputs()`

```python
# In dashboard dict, add:
"research": {
    "available": bool(llm_status.get("tier3_results")),
    "temporal_patterns": llm_status.get("tier3_results", {}).get("temporal") is not None,
    "failure_clusters": llm_status.get("tier3_results", {}).get("failure_clusters") is not None,
}
```

### Fix 3: Integrate Research into CustDev

**File:** `pipeline/custdev.py:build_custdev()`

```python
# Add parameter for research results
def build_custdev(df, features, research_results=None, ...):
    # If research_results.custdev exists, merge with keyword results
    if research_results and research_results.get("custdev"):
        llm_insights = research_results["custdev"]
        # Merge with categories
```

### Fix 4: Add /research Frontend Route

**File:** `frontend/src/App.tsx`

```typescript
// Add route:
<Route path="/research" element={<Research />} />

// Create: frontend/src/pages/Research.tsx
```

---

## Data Quality Checklist

| Stage | Input | Output | Format | Cached? |
|-------|-------|--------|--------|---------|
| Ingest | CSV/Sheet | DataFrame | Raw | Yes (raw.csv) |
| Profile | DataFrame | Profile | Dict | No |
| Classify | Dialogue text | Analysis | Dict | No |
| LLM Tier 1 | 180 calls | Batch results | Dict | Yes (.llm_cache/) |
| LLM Tier 2 | Flagged calls | Detailed | Dict | Yes (.llm_cache/) |
| LLM Tier 3 | Aggregated | Research | Dict | No |
| Metrics | Flattened DF | Metrics | Dict | No |
| Output | All | JSON files | JSON | No |

---

## Recommendations

### Immediate (High Priority)
1. ✅ **Update batch size to 180** — DONE
2. ⚠️ **Persist Tier 3 results** — Add research.json output
3. ⚠️ **Update dashboard.json** — Include research metadata
4. ⚠️ **Integrate research into custdev** — Merge LLM insights

### Short-term (Medium Priority)
5. **Add /research frontend page** — Display Tier 3 insights
6. **Add research.json loading hook** — frontend/src/hooks.ts
7. **Update llm_status schema** — Include tier breakdown

### Long-term (Low Priority)
8. **Tier 3 result caching** — Cache research queries
9. **Real-time Tier 3** — Run on-demand, not just pipeline
10. **Research A/B testing** — Compare insights over time

---

*Verification Date: 2026-06-06*
*Status: Issues Identified, Fixes Documented*
