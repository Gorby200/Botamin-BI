import type { Band, Fmt } from "./types";

/** Format a metric value according to its declared format.

  PRECISION: 2 decimals for percentages (BI dashboard accuracy).
  Consistency across all metrics reduces cognitive load.
*/
export function fmtValue(value: number, fmt: Fmt): string {
  switch (fmt) {
    case "pct":
      return `${(value * 100).toFixed(2)}%`;
    case "ratio":
      return value.toFixed(2);
    case "int":
      return Math.round(value).toLocaleString("ru-RU");
    case "sec": {
      const m = Math.floor(value / 60);
      const s = Math.round(value % 60);
      return `${m}:${s.toString().padStart(2, "0")}`;
    }
    case "float":
      return value.toFixed(2);
    default:
      return String(value);
  }
}

/** Format as percentage with configurable decimals (default: 2 for BI precision). */
export function pct(v: number, d = 2): string {
  return `${(v * 100).toFixed(d)}%`;
}

export function fmtDuration(sec: number): string {
  const m = Math.floor(sec / 60);
  const s = Math.floor(sec % 60);
  return `${m}:${s.toString().padStart(2, "0")}`;
}

/** Human label for a threshold rule, e.g. "цель ≥ 50% · приемлемо ≥ 30%". */
export function thresholdLabel(
  th: { good: number; ok: number; direction: "higher" | "lower" } | null,
  fmt: Fmt
): string {
  if (!th) return "";
  const op = th.direction === "higher" ? "≥" : "≤";
  return `цель ${op} ${fmtValue(th.good, fmt)} · приемлемо ${op} ${fmtValue(th.ok, fmt)}`;
}

export const bandText: Record<Band, string> = {
  good: "band-good",
  ok: "band-ok",
  bad: "band-bad",
  neutral: "band-neutral",
};
export const bandChip: Record<Band, string> = {
  good: "bandbg-good",
  ok: "bandbg-ok",
  bad: "bandbg-bad",
  neutral: "bandbg-neutral",
};
export const bandBar: Record<Band, string> = {
  good: "band-bar-good",
  ok: "band-bar-ok",
  bad: "band-bar-bad",
  neutral: "band-bar-neutral",
};

export const stageLabels: Record<number, string> = {
  [-1]: "Нет контакта",
  0: "Контакт",
  1: "Согласие",
  2: "Оффер",
  3: "Встреча",
  4: "Квалификация",
};
