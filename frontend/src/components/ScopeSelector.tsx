/**
 * Analysis-scope segmented control, shared by the top banner (read-only state) and
 * the Settings page (interactive). Scope is applied at PIPELINE-RUN time (the data is
 * precomputed), so the interactive mode persists the chosen scope and the caller shows
 * how to apply it (CLI flag / GitHub Actions input) — it never silently lies about
 * re-analysing in the browser.
 */
export const SCOPES: { v: string; l: string; title: string }[] = [
  { v: "focus", l: "Focus", title: "Focus — LLM разбирает только содержательные диалоги (дёшево, точно там, где важно)" },
  { v: "full", l: "Full", title: "Full — LLM разбирает все состоявшиеся разговоры (дороже, максимальное покрытие)" },
  { v: "sample", l: "Sample", title: "Sample — калибровочная выборка разбирается LLM, остальное детерминированно" },
  { v: "off", l: "Off", title: "Off — только детерминированный анализ на правилах, без LLM" },
];

export default function ScopeSelector({
  active,
  onChange,
  size = "sm",
}: {
  active: string;
  onChange?: (v: string) => void;
  size?: "sm" | "md";
}) {
  const interactive = typeof onChange === "function";
  const pad = size === "md" ? "px-3 py-1 text-xs" : "px-2 py-0.5 text-[11px]";
  return (
    <div
      className="inline-flex items-center rounded-full border border-[var(--color-border)] bg-[var(--color-bg-card)] p-0.5"
      role={interactive ? "radiogroup" : "group"}
      aria-label="Охват анализа"
    >
      {SCOPES.map((s) => {
        const on = s.v === active;
        const base = `${pad} rounded-full font-medium leading-none transition-colors`;
        const state = on
          ? "bg-[var(--color-accent)] text-white"
          : "text-[var(--color-ink-tertiary)] hover:text-[var(--color-ink)]";
        if (interactive) {
          return (
            <button
              key={s.v}
              type="button"
              role="radio"
              aria-checked={on}
              title={s.title}
              onClick={() => onChange!(s.v)}
              className={`${base} ${state} cursor-pointer ${on ? "" : "hover:bg-[var(--color-bg-card-hover)]"}`}
            >
              {s.l}
            </button>
          );
        }
        return (
          <span key={s.v} title={s.title} className={`${base} ${state} cursor-help`}>
            {s.l}
          </span>
        );
      })}
    </div>
  );
}
