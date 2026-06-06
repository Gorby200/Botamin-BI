import { Sparkles, ShieldHalf, Info } from "lucide-react";
import type { LLMStatus } from "../types";
import ScopeSelector from "./ScopeSelector";

/**
 * Top banner: HOW the data was analysed, on ONE compact line.
 *  - mode starts with "llm" → green (LLM active); otherwise amber (deterministic failsafe).
 *  - A small segmented control on the right shows the analysis SCOPE (depth), with the
 *    active segment highlighted. It is informational (build-time flag), explained by the ⓘ.
 */
export default function AnalysisBanner({ llm }: { llm: LLMStatus }) {
  const isLLM = String(llm.mode || "").startsWith("llm");
  return (
    <div
      className={`flex items-center gap-3 rounded-[var(--radius-md)] border px-3.5 py-2 text-xs ${
        isLLM
          ? "border-[var(--color-band-good)]/30 bandbg-good"
          : "border-[var(--color-band-ok)]/30 bandbg-ok"
      }`}
    >
      <span className="flex items-center gap-1.5 font-medium shrink-0">
        {isLLM ? <Sparkles size={13} /> : <ShieldHalf size={13} />}
        {isLLM ? `LLM · ${llm.provider}` : "Failsafe (LLM выкл.)"}
      </span>

      <span className="min-w-0 truncate text-[var(--color-ink-secondary)] hidden sm:inline">
        {isLLM
          ? `разобрано ${llm.calls_analyzed.toLocaleString("ru-RU")} из ${llm.calls_selected.toLocaleString("ru-RU")} диалогов`
          : llm.note || "метрики посчитаны детерминированными правилами"}
      </span>

      <span className="ml-auto flex items-center gap-2 shrink-0">
        <span className="text-[10px] uppercase tracking-wide text-[var(--color-ink-muted)]">Охват</span>
        <ScopeSelector active={llm.scope} />
        <span
          className="text-[var(--color-ink-muted)] cursor-help"
          title="Глубина разбора задаётся при сборке пайплайна: --llm-scope (focus / full / sample / off). Данные предрасчитаны, поэтому переключатель показывает текущий режим."
        >
          <Info size={12} />
        </span>
      </span>
    </div>
  );
}
