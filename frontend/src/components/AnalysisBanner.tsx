import { Sparkles, ShieldHalf, Info } from "lucide-react";
import type { LLMStatus } from "../types";

const SCOPE_LABEL: Record<string, string> = {
  focus: "Фокус · содержательные диалоги",
  full: "Полный · все разговоры",
  sample: "Выборка · калибровка",
  off: "Выключено",
};

/**
 * Top banner showing HOW the data was analysed.
 *  - mode === "llm"  -> green: deep LLM analysis is active
 *  - otherwise       -> amber: deterministic failsafe ("LLM недоступна")
 * Also surfaces the "Глубина разбора" depth switch (focus/full) so the reader
 * knows the coverage. The switch itself is a build-time flag (--llm-scope), since
 * the data is precomputed; the banner explains how to change it.
 */
export default function AnalysisBanner({ llm }: { llm: LLMStatus }) {
  const isLLM = llm.mode === "llm";
  return (
    <div
      className={`flex flex-wrap items-center gap-x-4 gap-y-1.5 rounded-[var(--radius-md)] border px-4 py-2.5 text-xs ${
        isLLM
          ? "border-[var(--color-band-good)]/30 bandbg-good"
          : "border-[var(--color-band-ok)]/30 bandbg-ok"
      }`}
    >
      <span className="flex items-center gap-1.5 font-medium">
        {isLLM ? <Sparkles size={14} /> : <ShieldHalf size={14} />}
        {isLLM ? `LLM-анализ · ${llm.provider}` : "Упрощённый анализ (failsafe)"}
      </span>

      {isLLM ? (
        <span className="text-[var(--color-ink-secondary)]">
          разобрано {llm.calls_analyzed.toLocaleString("ru-RU")} из{" "}
          {llm.calls_selected.toLocaleString("ru-RU")} диалогов · глубина:{" "}
          {SCOPE_LABEL[llm.scope] || llm.scope}
        </span>
      ) : (
        <span className="text-[var(--color-ink-secondary)]">
          {llm.note || "LLM-модель недоступна — метрики посчитаны детерминированными правилами."}
        </span>
      )}

      <span className="ml-auto flex items-center gap-1.5 text-[var(--color-ink-tertiary)]">
        <Info size={12} />
        {isLLM
          ? "Переключить охват: --llm-scope full"
          : "Включить LLM: задайте ключ в .env и пересоберите"}
      </span>
    </div>
  );
}
