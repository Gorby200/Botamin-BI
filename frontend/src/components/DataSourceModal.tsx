import { useState } from "react";
import { X, Upload, Loader2, ExternalLink, CheckCircle2 } from "lucide-react";

interface Props {
  onClose: () => void;
}

const REPO_NAME = "Gorby200/Botamin-BI";

export default function DataSourceModal({ onClose }: Props) {
  const [step, setStep] = useState<"input" | "redirecting" | "success">("input");
  const [sheetUrl, setSheetUrl] = useState("");
  const [llmScope, setLlmScope] = useState<"off" | "focus" | "full" | "sample">("focus");

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!sheetUrl.trim()) return;

    setStep("redirecting");

    // Open GitHub Actions in new tab
    const params = new URLSearchParams({
      sheet_url: sheetUrl.trim(),
      llm_scope: llmScope,
    });

    const actionsUrl = `https://github.com/${REPO_NAME}/actions/workflows/deploy.yml`;
    const runUrl = `${actionsUrl}?${params.toString()}`;

    window.open(runUrl, "_blank");

    // Show success message after redirect
    setTimeout(() => setStep("success"), 1000);
  };

  return (
    <>
      <div className="fixed inset-0 bg-black/30 z-40" onClick={onClose} />
      <div className="fixed inset-0 flex items-center justify-center z-50 p-4">
        <div className="bg-[var(--color-bg-card)] rounded-2xl shadow-[var(--shadow-drawer)] max-w-md w-full border border-[var(--color-border)]">
          {/* Header */}
          <div className="flex items-center justify-between p-6 border-b border-[var(--color-border)]">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-full bg-[var(--color-accent-subtle)] flex items-center justify-center">
                <Upload size={20} className="text-[var(--color-accent)]" />
              </div>
              <div>
                <h3 className="text-base font-medium">Загрузка данных</h3>
                <p className="text-xs text-[var(--color-ink-muted)]">
                  {step === "input" && "Укажи источник данных для анализа"}
                  {step === "redirecting" && "Перенаправление в GitHub Actions..."}
                  {step === "success" && "Запущен анализ данных"}
                </p>
              </div>
            </div>
            <button onClick={onClose} className="p-1.5 rounded-[var(--radius-sm)] hover:bg-[var(--color-bg-card-hover)]">
              <X size={18} />
            </button>
          </div>

          {/* Content */}
          <div className="p-6">
            {step === "input" && (
              <form onSubmit={handleSubmit} className="space-y-4">
                <div>
                  <label className="block text-sm font-medium mb-2">
                    Google Sheets URL
                  </label>
                  <input
                    type="url"
                    value={sheetUrl}
                    onChange={(e) => setSheetUrl(e.target.value)}
                    placeholder="https://docs.google.com/spreadsheets/d/..."
                    className="w-full px-4 py-2.5 rounded-[var(--radius-md)] border border-[var(--color-border)] bg-[var(--color-bg-card-hover)] text-sm focus:outline-none focus:border-[var(--color-accent)]"
                    required
                  />
                  <p className="mt-2 text-xs text-[var(--color-ink-muted)]">
                    Файл должен быть доступен по ссылке "Anyone with the link can view"
                  </p>
                </div>

                <div>
                  <label className="block text-sm font-medium mb-2">
                    Глубина LLM-анализа
                  </label>
                  <div className="grid grid-cols-2 gap-2">
                    {[
                      { v: "off", l: "Без LLM" },
                      { v: "focus", l: "Focus (рекомендуется)" },
                      { v: "full", l: "Полный" },
                      { v: "sample", l: "Выборка" },
                    ].map((opt) => (
                      <button
                        key={opt.v}
                        type="button"
                        onClick={() => setLlmScope(opt.v as any)}
                        className={`px-3 py-2 rounded-[var(--radius-md)] text-xs font-medium transition-colors ${
                          llmScope === opt.v
                            ? "bg-[var(--color-accent)] text-white"
                            : "bg-[var(--color-bg-card-hover)] text-[var(--color-ink-secondary)] hover:bg-[var(--color-border)]"
                        }`}
                      >
                        {opt.l}
                      </button>
                    ))}
                  </div>
                  <p className="mt-2 text-xs text-[var(--color-ink-muted)]">
                    {llmScope === "off" && "Только детерминированный анализ (быстро)"}
                    {llmScope === "focus" && "Анализ диалогов с 3+ репликами клиента"}
                    {llmScope === "full" && "Все подключившиеся звонки"}
                    {llmScope === "sample" && "Случайная выборка 100 звонков"}
                  </p>
                </div>

                <div className="pt-2">
                  <button
                    type="submit"
                    disabled={!sheetUrl.trim()}
                    className="w-full py-2.5 rounded-[var(--radius-md)] bg-[var(--color-accent)] text-white font-medium text-sm disabled:opacity-50 disabled:cursor-not-allowed hover:opacity-90 transition-opacity flex items-center justify-center gap-2"
                  >
                    <Upload size={16} />
                    Запустить анализ
                  </button>
                </div>
              </form>
            )}

            {step === "redirecting" && (
              <div className="text-center py-8">
                <Loader2 size={40} className="mx-auto animate-spin text-[var(--color-accent)]" />
                <p className="mt-4 text-sm text-[var(--color-ink-secondary)]">
                  Открываю GitHub Actions...
                </p>
              </div>
            )}

            {step === "success" && (
              <div className="text-center py-6">
                <div className="w-16 h-16 rounded-full bg-[var(--color-band-good)]/20 flex items-center justify-center mx-auto mb-4">
                  <CheckCircle2 size={32} className="text-[var(--color-band-good)]" />
                </div>
                <h4 className="text-base font-medium mb-2">Анализ запущен!</h4>
                <p className="text-sm text-[var(--color-ink-secondary)] mb-6">
                  GitHub Actions обрабатывает твои данные. Это займёт 2-3 минуты.
                </p>
                <a
                  href={`https://github.com/${REPO_NAME}/actions`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-2 px-4 py-2 rounded-[var(--radius-md)] bg-[var(--color-bg-card-hover)] text-sm font-medium hover:bg-[var(--color-border)] transition-colors"
                >
                  <ExternalLink size={14} />
                  Следить за прогрессом
                </a>
                <button
                  onClick={onClose}
                  className="block w-full mt-3 py-2 text-sm text-[var(--color-ink-muted)] hover:text-[var(--color-ink-secondary)]"
                >
                  Закрыть
                </button>
              </div>
            )}
          </div>

          {/* Footer note */}
          {step === "input" && (
            <div className="px-6 pb-4">
              <div className="rounded-[var(--radius-md)] bg-[var(--color-bg-card-hover)] px-4 py-3">
                <p className="text-xs text-[var(--color-ink-muted)] leading-relaxed">
                  <strong>Как это работает:</strong> После нажатия "Запустить" откроется GitHub Actions,
                  где нужно будет нажать "Run workflow". Через 2-3 минуты данные появятся на дашборде.
                </p>
              </div>
            </div>
          )}
        </div>
      </div>
    </>
  );
}
