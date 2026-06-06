# CustDev Integration — Product Decision
**2026-06-06 | Consolidation of Research into CustDev**

---

## Decision

**Unified CustDev Page:** Instead of separate /research and /custdev pages, we consolidated all customer insights into a single CustDev page with progressive enhancement.

---

## Rationale (Product Builder Perspective)

### Problem
- Initial implementation created separate `/research` page for Tier 3 insights
- This duplicated functionality and confused the domain model
- Users had to check two places for "voice of customer" insights

### Solution
**CustDev IS Research** — they are the same domain:
- **Basic CustDev:** Keyword-based extraction (deterministic fallback)
- **Enhanced CustDev:** LLM-based insights when available
- **Tier 3 Enhancement:** Cross-call patterns (temporal, failures, signals)

### Benefits
1. **Single source of truth** for customer insights
2. **Progressive enhancement** — works without LLM, better with LLM
3. **Fewer pages** — simpler navigation, less cognitive load
4. **Coherent UX** — all "voice of customer" data in one place

---

## Updated Page Structure

### CustDev Page (`/custdev`)

**Sections:**

1. **Header** — Page title with Tier 3 availability indicator
2. **Research Lens** — Editable prompt framing what we're looking for
3. **Live Filter** — Keyword filtering of quotes
4. **Summary** — What we heard (top themes with counts and recommendations)
5. **Tier 3 Insights** (when available):
   - Temporal Patterns — Time-of-day performance patterns
   - Failure Clustering — Typical loss scenarios
   - Conversion Signals — Predictors of meeting success
6. **Insight Clusters** — Category-based quotes (pain, wish, competitor, etc.)

### Behavior

**Without LLM:**
- Shows deterministic keyword-based insights
- Hides Tier 3 section (research.json not available)

**With LLM (Tier 1 + 2):**
- Shows LLM-extracted insights
- Mode indicator: "LLM" badge
- Hides Tier 3 section if research.json not available

**With LLM (Tier 3 enabled):**
- Shows all sections including Tier 3 insights
- Header indicator: "Доступны расширенные инсайты..."
- Displays temporal patterns, failure clusters, conversion signals

---

## Navigation Structure (Final)

| Order | Path | Label | Hint |
|-------|------|-------|------|
| 1 | `/` | Продукт | Общая картина |
| 2 | `/funnel` | Воронка | S0 → S4, где теряем |
| 3 | `/voice` | Голос. агент | Качество ведения диалога |
| 4 | `/technical` | Техника | Связь, ASR, инструментовка |
| 5 | `/calls` | Звонки | Просмотр диалогов |
| **6** | **`/custdev`** | **CustDev** | **Голос клиента, Tier 3 инсайты** |
| 7 | `/backlog` | Бэклог | Гипотезы и A/B |
| 8 | `/method` | Методика | Почему так |
| 9 | `/settings` | Настройки | Пороги метрик |

**Previous:** Separate `/research` entry (removed)

---

## Technical Implementation

### Files Modified

1. **`frontend/src/pages/CustDev.tsx`**
   - Added `useResearch()` hook integration
   - Added Tier 3 insights section (conditional on availability)
   - Updated header with Tier 3 indicator
   - Cards for temporal patterns, failure clusters, conversion signals

2. **`frontend/src/App.tsx`**
   - Removed `Brain` icon import
   - Removed `ResearchPage` lazy import
   - Removed `/research` navigation entry
   - Removed `/research` route
   - Updated CustDev hint: "Голос клиента, Tier 3 инсайты"

3. **`frontend/src/hooks.ts`**
   - Kept `useResearch()` hook (used by CustDev)
   - Handles 404 gracefully when research.json missing

### Files Deleted

1. **`frontend/src/pages/Research.tsx`**
   - Redundant after consolidation
   - Functionality integrated into CustDev

### Files Kept

1. **`frontend/src/types.ts`**
   - Kept Research types (used by CustDev)
   - Kept updated LLMStatus with tier3 fields

2. **`pipeline/llm/research.py`**
   - Unchanged — still generates research.json
   - Still called by orchestrator when Tier 3 enabled

3. **`pipeline/build.py`**
   - Unchanged — still writes research.json

---

## User Experience

### View 1: Deterministic Only (No LLM)
```
┌─────────────────────────────────────────┐
│ CustDev · голос клиента                 │
│ Что важного мы услышали...              │
└─────────────────────────────────────────┘
┌─────────────────────────────────────────┐
│ Тематика исследования                  │
│ [по ключевым словам]                    │
└─────────────────────────────────────────┘
┌─────────────────────────────────────────┐
│ Что мы важное услышали                 │
│ • Боли и проблемы (45) — зафиксировать...│
│ • Конкуренты (12) — отстройка...        │
└─────────────────────────────────────────┘
┌─────────────────────────────────────────┐
│ [Insight clusters with quotes]         │
└─────────────────────────────────────────┘
```

### View 2: With Tier 3 Research (LLM Enabled)
```
┌─────────────────────────────────────────┐
│ 💡 CustDev · голос клиента              │
│ Что важного мы услышали...              │
│ 🧠 Доступны расширенные инсайты...      │
└─────────────────────────────────────────┘
┌─────────────────────────────────────────┐
│ Тематика исследования [LLM]              │
└─────────────────────────────────────────┘
┌─────────────────────────────────────────┐
│ Что мы важное услышали                 │
└─────────────────────────────────────────┘
┌─────────────────────────────────────────┐
│ 🧠 LLM Tier 3 — кросс-анализ звонков   │
│                                         │
│ 🕐 Временные паттерны                  │
│   • 9:00-11:00 понедельник (65% meet)  │
│                                         │
│ ⚠️ Кластеры отказов                    │
│   • Weak Opener (23%) — сократить...    │
│                                         │
│ ⚡ Сигналы конверсии                   │
│   • Клиент задаёт вопросы (2.8x)       │
└─────────────────────────────────────────┘
┌─────────────────────────────────────────┐
│ [Insight clusters with quotes]         │
└─────────────────────────────────────────┘
```

---

## Design Principles Applied

1. **Progressive Enhancement**
   - Base functionality works without LLM
   - Enhanced experience when Tier 3 available
   - Graceful degradation when research.json missing

2. **Single Responsibility**
   - CustDev page owns ALL customer insights
   - No duplication across pages

3. **User-Centric Navigation**
   - Clear domain: "Голос клиента" = all things customer
   - Fewer pages = easier to understand

4. **Fail-Safe Architecture**
   - Each section independently optional
   - Missing data = hide section, don't break page

---

## Migration Notes

**For Users:**
- No change in URL — still `/custdev`
- Enhanced page when Tier 3 available
- Same familiar layout with new sections below

**For Developers:**
- useResearch() hook still available for other pages
- Research types still defined in types.ts
- research.json still generated by pipeline

---

## Future Considerations

**Potential Enhancements:**
1. Add expand/collapse for Tier 3 section
2. Add "See full analysis" link if we want dedicated view later
3. Add interactive filtering for Tier 3 insights

**NOT Planned:**
- Separate `/research` page (against consolidation principle)

---

*Decision Date: 2026-06-06*
*Decision Maker: Product Architect (50+ years experience)*
*Status: Implemented*
*Rationale: Domain consolidation — CustDev and Research are one entity*
