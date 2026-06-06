// Threshold store + live re-banding.
//
// Architectural rule (PO): thresholds are CONFIG, not hardcode. The pipeline emits
// DEFAULTS (dashboard.thresholds_defaults) + raw values + the full comment map.
// The user edits overrides on the Settings page; we persist them to localStorage
// and RE-BAND every metric live — no pipeline re-run needed for "Пересчитать".

import { useSyncExternalStore } from "react";
import type { Band, Dashboard, Metric, ThresholdDef, Fmt } from "./types";

export type Override = { good: number; ok: number };
export type Overrides = Record<string, Override>;

const LS_KEY = "botamin.thresholds.v1";

function load(): Overrides {
  try {
    return JSON.parse(localStorage.getItem(LS_KEY) || "{}");
  } catch {
    return {};
  }
}

let overrides: Overrides = load();
const listeners = new Set<() => void>();

export function getOverrides(): Overrides {
  return overrides;
}
export function setOverrides(o: Overrides): void {
  overrides = o;
  try {
    localStorage.setItem(LS_KEY, JSON.stringify(o));
  } catch {
    /* ignore quota */
  }
  listeners.forEach((l) => l());
}
export function resetOverrides(): void {
  setOverrides({});
}
function subscribe(l: () => void): () => void {
  listeners.add(l);
  return () => listeners.delete(l);
}

/** React hook: current overrides (re-renders subscribers on change). */
export function useOverrides(): Overrides {
  return useSyncExternalStore(subscribe, getOverrides, getOverrides);
}

const VERDICT: Record<Band, string> = {
  good: "Хорошо",
  ok: "Приемлемо",
  bad: "Требует внимания",
  neutral: "",
};

export function bandOf(value: number, good: number, ok: number, direction: "higher" | "lower"): Band {
  if (direction === "higher") return value >= good ? "good" : value >= ok ? "ok" : "bad";
  return value <= good ? "good" : value <= ok ? "ok" : "bad";
}

/** Re-band one metric using active thresholds (defaults ⊕ overrides). */
export function rebandMetric(
  m: Metric,
  defs: Record<string, ThresholdDef>,
  ov: Overrides
): Metric {
  if (!m.thr_key) return m;
  const def = defs[m.thr_key];
  if (!def) return m;
  const good = ov[m.thr_key]?.good ?? def.good;
  const ok = ov[m.thr_key]?.ok ?? def.ok;
  const band = bandOf(m.value, good, ok, def.direction);
  return {
    ...m,
    band,
    verdict: VERDICT[band],
    comment: m.comments?.[band] ?? m.comment,
    thresholds: { good, ok, direction: def.direction },
  };
}

/** Return a copy of the dashboard with every metric re-banded by active thresholds. */
export function applyThresholds(d: Dashboard, ov: Overrides): Dashboard {
  const defs: Record<string, ThresholdDef> = {};
  (d.thresholds_defaults || []).forEach((t) => (defs[t.key] = t));
  const rb = (m: Metric) => rebandMetric(m, defs, ov);
  return {
    ...d,
    reach: { ...d.reach, metrics: d.reach.metrics.map(rb) },
    drivers: d.drivers.map((x) => rb(x as Metric) as typeof x),
    nsm: rb(d.nsm) as typeof d.nsm,
    quality: { ...d.quality, metrics: d.quality.metrics.map(rb) },
    guardrails: d.guardrails.map(rb),
  };
}

/** Auto-derive thresholds anchored to the CURRENT dataset value.
 *  ok = your current level (acceptable floor); good = a realistic stretch. */
export function autoFromValue(
  value: number,
  direction: "higher" | "lower",
  fmt: Fmt
): Override {
  const clamp = (v: number) => (fmt === "sec" || fmt === "int" ? Math.max(0, v) : Math.min(1, Math.max(0, v)));
  const round = (v: number) =>
    fmt === "sec" ? Math.round(v) : fmt === "int" ? Math.round(v) : Math.round(v * 1000) / 1000;
  // Anchor `ok` to the EXACT current value so today's level always qualifies as
  // at least "приемлемо" (no rounding it past the value). `good` is a rounded stretch.
  const okAnchor = clamp(value);
  if (direction === "higher") {
    return { ok: okAnchor, good: round(clamp(value * 1.25)) };
  }
  // lower-is-better: good is the tighter (lower) target
  return { good: round(clamp(value * 0.75)), ok: okAnchor };
}
