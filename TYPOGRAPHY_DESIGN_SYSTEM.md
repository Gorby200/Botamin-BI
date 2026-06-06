# Botamin BI — Typography & Number Design System
**2026-06-06 | UI/UX Design Standards**

---

## Design Principles

1. **Consistency > Variety** — One way to do each thing
2. **Precision Matters** — 2 decimals for BI accuracy
3. **Scannability** — Tabular numbers for data
4. **Clear Hierarchy** — Font families signal purpose

---

## Decimal Precision

### Standard: 2 Decimal Places

**Before:** `12.3%` (1 decimal)
**After:** `12.34%` (2 decimals)

### Rationale

| Concern | Response |
|---------|----------|
| "Too many digits?" | Tabular nums make it scannable |
| "Cluttered?" | Consistency reduces cognitive load |
| "When to use?" | Everywhere — no mixing |
| "Why 2 not 1?" | Small deltas are business-critical |

### Examples

```
✓ 12.34%  — consistent, precise
✓ 45.67%  — shows meaningful difference from 45.12%
✓ 8.91%   — captures trend direction

✗ 12.3%   — loses precision
✗ 45.67%  — inconsistent
✗ 8.9%    — inconsistent
```

### Implementation

**format.ts:**
```typescript
export function fmtValue(value: number, fmt: Fmt): string {
  switch (fmt) {
    case "pct":
      return `${(value * 100).toFixed(2)}%`;  // Was .toFixed(1)
    ...
  }
}

export function pct(v: number, d = 2): string {  // Was d = 1
  return `${(v * 100).toFixed(d)}%`;
}
```

---

## Typography Scale

### Font Families

| Purpose | Font | Usage |
|---------|------|-------|
| Display | Fraunces Variable (serif) | H1 page titles |
| Body/UI | Hanken Grotesk Variable (sans) | All text |
| Data | Hanken Grotesk + tabular-nums | Metric numbers |
| Code | Geist Mono | Technical terms |

### Size Scale

| Class | Size | Weight | Usage |
|-------|------|--------|-------|
| `.page-title` | 1.5rem (24px) | 500 | H1 page headers |
| `.section-label` | 0.875rem (14px) | 500 | H2 section headers |
| `.card-title` | 0.875rem (14px) | 500 | Card titles |
| body | 1rem (16px) | 400 | Default text |
| `.card-subtitle` | 0.75rem (12px) | 400 | Card subtitles |
| `.meta-text` | 0.75rem (12px) | 400 | Dates, sources |

### Hierarchy Pattern

```
┌─────────────────────────────────────────┐
│ H1: Продукт · общая картина            │  ← page-title (Fraunces)
│   Что важного мы услышали...            │  ← body (Hanken Grotesk)
├─────────────────────────────────────────┤
│ 📞 Дозвон и вовлечение · контекст...   │  ← section-label (uppercase)
├─────────────────────────────────────────┤
│ ┌─────────────────────────────────┐   │
│ │ Connect Rate                    │   │  ← card-title
│ │ Proportion of dials that...     │   │  ← card-subtitle
│ │ 65.23%                          │   │  ← stat-num (2 decimals)
│ └─────────────────────────────────┘   │
└─────────────────────────────────────────┘
```

---

## Section Headers Pattern

### Standard Pattern (from Overview)

```tsx
<div className="section-header">
  <PhoneCall size={14} className="text-[var(--color-accent)]" />
  <h2 className="section-label">Дозвон и вовлечение</h2>
  <span className="section-hint">· Контекстный слой</span>
</div>
```

**Rules:**
1. Icon: 14px (icon-sm), accent color
2. Label: Uppercase, tracking-wider, ink-secondary
3. Hint: After · separator, ink-muted

### Icon Standards

| Size | Class | Usage |
|------|-------|-------|
| 12px | icon-xs | Very small indicators |
| 14px | icon-sm | Section headers, inline (DEFAULT) |
| 16px | icon-md | Page-level icons |
| 18px | icon-lg | Hero section icons |

**Default:** Use 14px (icon-sm) unless context demands larger.

---

## Number Display

### The `.stat-num` Class

**Purpose:** All metric values use this class

```css
.stat-num {
  font-family: var(--font-sans);
  font-variant-numeric: tabular-nums lining-nums;  /* Key: fixed width */
  font-weight: 600;
  letter-spacing: -0.025em;
  font-feature-settings: "ss01";
}
```

**What it does:**
- Tabular-nums: Each digit has same width (prevents jitter)
- Lining-nums: Modern vs old-style figures
- Tight spacing: Dense but readable
- ss01: Alternative digit shapes (if available)

### Usage Examples

```tsx
// ✓ Correct — always use stat-num for data
<span className="stat-num">65.23%</span>

// ✗ Wrong — inline styling
<span style={{fontFamily: 'monospace'}}>65.23%</span>

// ✗ Wrong — no class
<span>65.23%</span>
```

---

## Color & Meaning

### Text Hierarchy

| Role | Color | Usage |
|------|-------|-------|
| Primary | `var(--color-ink)` | Main content |
| Secondary | `var(--color-ink-secondary)` | Supporting text |
| Tertiary | `var(--color-ink-tertiary)` | Subtitles, hints |
| Muted | `var(--color-ink-muted)` | Meta info |

### Band Colors (Metrics)

| Band | Use When | Color |
|------|----------|-------|
| good | Target met | Green/teal |
| ok | Acceptable | Amber/yellow |
| bad | Needs attention | Red/coral |
| neutral | No band | Gray |

---

## Page-by-Page Typography

### Overview (Reference Standard)

```tsx
<h1 className="page-title">              {/* Fraunces, 24px */}
  Продукт · общая картина
</h1>
<p className="text-sm text-[var(--color-ink-tertiary)]">
  Куда движется кампания...
</p>

<div className="section-header">
  <PhoneCall size={14} className="text-[var(--color-accent)]" />
  <h2 className="section-label">           {/* 14px uppercase */}
    Дозвон и вовлечение
  </h2>
</div>

<span className="stat-num">65.23%</span>   {/* Tabular, 2 decimals */}
```

### Funnel

```tsx
<h1 className="page-title">Воронка S0 → S4</h1>
<h2 className="section-label">Драйверы — 4 переходные конверсии</h2>
<span className="stat-num">{pct(f.conversion_from_prev)}</span>
```

### Technical

```tsx
<h1 className="page-title">Технические метрики</h1>
<div className="section-header">
  <Lock size={14} />
  <h2 className="section-label">
    Необходимо извлечь из оригинала записи
  </h2>
</div>
```

---

## Common Patterns

### Card with Title + Subtitle

```tsx
<Card
  title="Качество диалога"
  subtitle="Микс продуктовых и технических сигналов"
>
```

### Metric Card

```tsx
<StatCard
  m={{
    name: "Connect Rate",
    value: 0.6523,
    fmt: "pct",
    band: "good",
    comment: "Above target"
  }}
/>
// Displays: "65.23%" with green band
```

### Pattern Row (Compact)

```tsx
<StatRow m={metric} />
// Displays: Name | Verdict | Value
```

---

## Spacing System

| Context | Spacing |
|---------|---------|
| Page padding | `p-8 pt-5` (32px top, 20px bottom) |
| Section gaps | `space-y-7` (28px) |
| Card gaps | `gap-4` (16px) |
| Item gaps | `gap-2` or `gap-3` (8-12px) |

---

## Responsive Typography

| Breakpoint | H1 Size | Card Grid |
|------------|----------|-----------|
| Base | 24px | 1 column |
| md (768px) | 24px | 2-3 columns |
| lg (1024px) | 24px | 2 columns |
| xl (1280px) | 24px | 4-5 columns |

---

## Migration Checklist

To update a page to use standard typography:

- [ ] H1 uses `.page-title` (or inline style with font-display)
- [ ] H2 uses `.section-label` (uppercase, tracking-wider)
- [ ] Icons use standard sizes (14px default)
- [ ] Metric numbers use `.stat-num` class
- [ ] Percentages show 2 decimals
- [ ] Section headers follow icon + label + hint pattern
- [ ] Colors use semantic variables

---

## Design Tokens Reference

```css
/* Fonts */
--font-display: "Fraunces Variable", serif;
--font-sans: "Hanken Grotesk Variable", system-ui, sans-serif;
--font-mono: "Geist Mono", monospace;

/* Text colors */
--color-ink: oklch(0.24 0.012 60);
--color-ink-secondary: oklch(0.45 0.015 60);
--color-ink-tertiary: oklch(0.62 0.012 60);
--color-ink-muted: oklch(0.78 0.008 60);

/* Accent */
--color-accent: oklch(0.52 0.08 200);
--color-secondary: oklch(0.62 0.08 55);

/* Band colors */
--color-band-good: oklch(0.55 0.11 150);
--color-band-ok: oklch(0.58 0.10 75);
--color-band-bad: oklch(0.55 0.16 25);
```

---

*Design System Version: 1.0*
*Last Updated: 2026-06-06*
*Designer: UI/UX Architect (50+ years experience)*
