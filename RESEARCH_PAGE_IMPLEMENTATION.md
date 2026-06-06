# Research Page Implementation — Tier 3 LLM Insights
**2026-06-06 | Frontend Integration Complete**

---

## Overview

Implemented the `/research` frontend page to display **Tier 3 LLM insights** from the three-tier LLM architecture. This completes the full data pipeline from CSV ingestion → Analysis → Frontend visualization.

---

## Files Created

### 1. `frontend/src/pages/Research.tsx`
**Purpose:** Display Tier 3 cross-call insights

**Sections:**
- **Header** with analysis metadata (calls analyzed, generated timestamp)
- **Status Banner** showing LLM configuration and available insight types
- **Temporal Patterns** — Time-of-day/day-of-week performance patterns
- **Failure Clustering** — Grouped failure modes with hypotheses and fixes
- **Conversion Signals** — Positive and negative predictors of meeting success
- **CustDev Insights** — Voice of customer insights and hypotheses

**Features:**
- Graceful handling when research.json is not available (404 is OK)
- Visual indicators for each insight type availability
- Detailed cards with metrics, quotes, and recommendations
- Responsive grid layouts for different screen sizes

---

## Files Modified

### 1. `frontend/src/types.ts`
**Added:** Research data type definitions

```typescript
export interface ResearchData {
  generated_at: string;
  total_calls_analyzed: number;
  temporal: TemporalAnalysis | null;
  failure_clusters: FailureClustering | null;
  conversion_signals: ConversionSignals | null;
  custdev: CustDevResearch | null;
}
```

**Also added:**
- `TemporalPattern`, `TemporalWarning`, `TemporalAnalysis`
- `FailureCluster`, `FailureClustering`
- `ConversionSignal`, `ConversionSignals`
- `CustDevInsight`, `CustDevHypothesis`, `CustDevResearch`

### 2. `frontend/src/hooks.ts`
**Added:** `useResearch()` hook

```typescript
export function useResearch() {
  // Fetches data/research.json
  // Handles 404 gracefully (research.json is optional)
  // Returns { data, loading, error }
}
```

**Behavior:**
- 404 errors are treated as "no data available" (not an error)
- Other HTTP errors are caught and reported
- Matches the pattern of other hooks (useDashboard, useCustDev, etc.)

### 3. `frontend/src/App.tsx`
**Changes:**
- Added `Brain` icon import from lucide-react
- Added `ResearchPage` lazy import
- Added research navigation item: `{ to: "/research", icon: Brain, label: "Research", hint: "Tier 3: кросс-анализ" }`
- Added route: `<Route path="/research" element={<ResearchPage />} />`

### 4. `pipeline/build.py`
**Changes:**
- Added `logging` import
- Added `logger = logging.getLogger(__name__)`

**Fixes a bug:** `logger.info()` was called but logger wasn't imported.

---

## Data Flow

```
┌─────────────────────────────────────────────────────────────────────────┐
│                      LLM TIER 3: RESEARCH                               │
│              (pipeline/llm/research.py)                                 │
├─────────────────────────────────────────────────────────────────────────┤
│  Functions:                                                            │
│    - temporal_analysis() → TemporalAnalysis                           │
│    - failure_clustering() → FailureClustering                          │
│    - conversion_signals() → ConversionSignals                          │
│    - custdev_extraction() → CustDevResearch                           │
│                                                                         │
│  Output: research.json                                                 │
└────────────────────────────────────┬────────────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                    FRONTEND: Research Page                               │
│                    (frontend/src/pages/Research.tsx)                   │
├─────────────────────────────────────────────────────────────────────────┤
│  Hook: useResearch() → loads research.json                             │
│                                                                         │
│  Sections:                                                              │
│    - Temporal Patterns (Clock icon)                                    │
│    - Failure Clusters (AlertTriangle icon)                             │
│    - Conversion Signals (Zap icon)                                     │
│    - CustDev Insights (Lightbulb icon)                                 │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Navigation Structure

The Research page is positioned between CustDev and Backlog in the sidebar:

| Order | Path | Label | Hint |
|-------|------|-------|------|
| 1 | `/` | Продукт | Общая картина |
| 2 | `/funnel` | Воронка | S0 → S4, где теряем |
| 3 | `/voice` | Голос. агент | Качество ведения диалога |
| 4 | `/technical` | Техника | Связь, ASR, инструментовка |
| 5 | `/calls` | Звонки | Просмотр диалогов |
| 6 | `/custdev` | CustDev | Голос клиента, инсайты |
| **7** | **`/research`** | **Research** | **Tier 3: кросс-анализ** |
| 8 | `/backlog` | Бэклог | Гипотезы и A/B |
| 9 | `/method` | Методика | Почему так |
| 10 | `/settings` | Настройки | Пороги метрик |

---

## Usage

### For Users

1. Navigate to `/research` in the dashboard
2. View Tier 3 insights if available (after pipeline run with LLM)
3. If not available:
   - Check if LLM is configured (see status banner)
   - Run pipeline to generate research.json
   - Page will auto-refresh on next load

### For Developers

**To generate research.json:**
```bash
# Ensure LLM key is configured in .env
LLM_API_KEY=your_key python -m pipeline build --file-path data/sample.csv
```

**Research.json structure:**
```json
{
  "generated_at": "2026-06-06T12:34:56",
  "total_calls_analyzed": 2000,
  "temporal": {
    "patterns": [...],
    "warnings": [...],
    "overall_insights": "..."
  },
  "failure_clusters": {
    "clusters": [...],
    "priority_order": [...],
    "quick_wins": [...]
  },
  "conversion_signals": {
    "strong_signals": [...],
    "negative_predictors": [...],
    "surprising_findings": "...",
    "scoring_model": {...}
  },
  "custdev": {
    "insights": [...],
    "new_hypotheses": [...]
  }
}
```

---

## Design Decisions

### 1. 404 Handling
**Decision:** Treat missing research.json as "no data" rather than error
**Reason:** Research is optional enhancement, not core functionality
**Implementation:** useResearch hook catches 404 and returns null data with no error

### 2. Component Pattern
**Decision:** Follow existing page pattern (CustDev.tsx)
**Reason:** Consistency in codebase, familiar UI patterns
**Implementation:** Similar Card usage, status indicators, empty states

### 3. Icon Choice
**Decision:** Brain icon for Research navigation
**Reason:** Represents "higher-level" thinking/analysis across calls
**Differentiation:** Distinct from Lightbulb (CustDev) which is more about "ideas"

### 4. Layout
**Decision:** Single-column with internal grids
**Reason:** Research insights are text-heavy, need width for quotes
**Implementation:** max-w-[1100px] like CustDev for readability

---

## Integration Checklist

- [x] Research types added to types.ts
- [x] useResearch hook added to hooks.ts
- [x] Research page component created
- [x] Route added to App.tsx
- [x] Navigation item added to sidebar
- [x] LLMStatus type updated with tier3 fields
- [x] Logger import fixed in build.py
- [x] 404 handling for missing research.json

---

## Testing

**To test:**
1. Start frontend dev server
2. Navigate to `/research`
3. Verify empty state shows correctly
4. Run pipeline with LLM to generate research.json
5. Verify page displays insights correctly

**Expected behavior:**
- Without research.json: Shows "Tier 3 Research — Недоступно" card
- With research.json: Shows all available insight sections
- Each section shows relevant metrics, quotes, recommendations

---

## Future Enhancements

1. **Interactive filtering** — Filter insights by category, time range
2. **Comparison view** — Compare insights across time periods
3. **Action buttons** — Direct link to Backlog from insights
4. **Export** — Download research insights as PDF/CSV
5. **Real-time updates** — Auto-refresh when pipeline completes

---

*Implementation Date: 2026-06-06*
*Status: Complete and Ready for Use*
