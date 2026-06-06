import { Info } from "lucide-react";
import type { Metric } from "../types";
import { fmtValue, thresholdLabel, bandText, bandChip, bandBar } from "../format";

/** Hover popover with the metric's definition, rationale, and thresholds.
 *  Pure CSS group-hover — no extra dependency. */
function InfoPopover({ m }: { m: Metric }) {
  return (
    <span className="group/info relative inline-flex shrink-0">
      <Info
        size={14}
        className="text-[var(--color-ink-muted)] hover:text-[var(--color-accent)] cursor-help transition-colors"
        strokeWidth={1.8}
      />
      <span
        className="pointer-events-none absolute right-0 top-6 z-50 w-72 origin-top-right scale-95 opacity-0 transition-all duration-150
                   group-hover/info:scale-100 group-hover/info:opacity-100
                   rounded-[var(--radius-md)] border border-[var(--color-border)] bg-[var(--color-bg-card)] p-3 shadow-[var(--shadow-drawer)]"
      >
        <span className="block text-xs font-medium text-[var(--color-ink)] mb-1">{m.name}</span>
        {m.desc && <span className="block text-[11px] leading-relaxed text-[var(--color-ink-secondary)] mb-2">{m.desc}</span>}
        {m.why && (
          <span className="block text-[11px] leading-relaxed text-[var(--color-ink-tertiary)] mb-2">
            <b className="text-[var(--color-ink-secondary)]">Зачем:</b> {m.why}
          </span>
        )}
        {m.thresholds && (
          <span className="block text-[10px] tabular-nums text-[var(--color-ink-muted)]">
            {thresholdLabel(m.thresholds, m.fmt)}
          </span>
        )}
      </span>
    </span>
  );
}

export function Verdict({ band, text }: { band: Metric["band"]; text: string }) {
  if (band === "neutral" || !text) return null;
  return (
    <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-medium ${bandChip[band]}`}>
      {text}
    </span>
  );
}

/** Large KPI card with band-coloured left bar, big grotesk number, verdict chip,
 *  numerator/denominator hint, dynamic comment, and an info popover. */
export function StatCard({ m, size = "md" }: { m: Metric; size?: "lg" | "md" }) {
  const num = size === "lg" ? "text-[2.75rem] leading-none" : "text-3xl";
  return (
    <div
      className={`relative rounded-[var(--radius-xl)] border border-[var(--color-border)] bg-[var(--color-bg-card)] p-5 ${bandBar[m.band]}
                  transition-shadow duration-[var(--duration-normal)] hover:shadow-[var(--shadow-card-hover)]`}
    >
      <div className="flex items-start justify-between gap-2 mb-2">
        <span className="text-[11px] font-medium uppercase tracking-wider text-[var(--color-ink-tertiary)]">
          {m.name}
        </span>
        <InfoPopover m={m} />
      </div>
      <div className="flex items-end gap-2.5">
        <span className={`stat-num ${num} ${bandText[m.band]}`}>{fmtValue(m.value, m.fmt)}</span>
        <span className="mb-1"><Verdict band={m.band} text={m.verdict} /></span>
      </div>
      {m.numerator != null && m.denominator != null && (
        <p className="mt-1.5 text-[11px] tabular-nums text-[var(--color-ink-muted)]">
          {m.numerator.toLocaleString("ru-RU")} / {m.denominator.toLocaleString("ru-RU")}
        </p>
      )}
      {m.comment && (
        <p className="mt-2 text-xs leading-relaxed text-[var(--color-ink-secondary)]">{m.comment}</p>
      )}
    </div>
  );
}

/** Compact row variant for dense lists (quality, guardrails). */
export function StatRow({ m }: { m: Metric }) {
  return (
    <div className="flex items-start justify-between gap-3 py-2.5 border-b border-[var(--color-border)] last:border-0">
      <div className="min-w-0">
        <div className="flex items-center gap-1.5">
          <span className="text-sm text-[var(--color-ink)]">{m.name}</span>
          <InfoPopover m={m} />
        </div>
        {m.comment && (
          <p className="mt-0.5 text-[11px] leading-snug text-[var(--color-ink-tertiary)] max-w-md">{m.comment}</p>
        )}
      </div>
      <div className="flex items-center gap-2 shrink-0">
        <Verdict band={m.band} text={m.verdict} />
        <span className={`stat-num text-lg ${bandText[m.band]}`}>{fmtValue(m.value, m.fmt)}</span>
      </div>
    </div>
  );
}
