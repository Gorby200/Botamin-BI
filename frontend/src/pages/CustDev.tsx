import { useState, useMemo } from "react";
import { useCustDev, useResearch } from "../hooks";
import Card from "../components/Card";
import Badge from "../components/Badge";
import Skeleton from "../components/Skeleton";
import { Lightbulb, Search, Quote, Sparkles, ShieldHalf, Clock, AlertTriangle, Zap, Brain } from "lucide-react";
import type { CustDevCategory } from "../types";

export default function CustDev() {
  const { data, loading } = useCustDev();
  const { data: research } = useResearch();
  const [lens, setLens] = useState("");
  const [filter, setFilter] = useState("");

  // initialise the editable lens from the precomputed prompt
  const promptValue = lens || data?.prompt || "";

  const keywords = useMemo(
    () => filter.toLowerCase().split(/[,\s]+/).map((s) => s.trim()).filter(Boolean),
    [filter]
  );

  const matchQuote = (q: string) =>
    keywords.length === 0 || keywords.some((k) => q.toLowerCase().includes(k));

  if (loading) return <div className="p-8 space-y-4"><Skeleton h={40} w={320} /><Skeleton h={200} /></div>;
  if (!data)
    return (
      <div className="p-8">
        <Card title="CustDev пока не сгенерирован">
          <p className="text-sm text-[var(--color-ink-secondary)]">
            Запустите пайплайн — он создаст <code>custdev.json</code> с инсайтами из транскриптов.
          </p>
        </Card>
      </div>
    );

  const isLLM = data.mode === "llm" || data.mode === "llm_research";
  const visibleCats = data.categories
    .map((c) => ({ ...c, quotes: c.quotes.filter((q) => matchQuote(q.quote)) }))
    .filter((c) => c.count > 0);

  // Tier 3 insights availability
  const hasTemporal = research?.temporal?.patterns?.length;
  const hasFailures = research?.failure_clusters?.clusters?.length;
  const hasSignals = research?.conversion_signals?.strong_signals?.length;
  const hasTier3 = hasTemporal || hasFailures || hasSignals;

  return (
    <div className="p-8 pt-5 space-y-7 max-w-[1100px]">
      <header>
        <h1 className="text-2xl flex items-center gap-2" style={{ fontFamily: "var(--font-display)" }}>
          <Lightbulb size={24} className="text-[var(--color-secondary)]" />
          CustDev · голос клиента
        </h1>
        <p className="mt-1 text-sm text-[var(--color-ink-tertiary)]">
          Что важного мы услышали в разговорах — прототип непрерывного кастдева.
          Инсайты + рекомендации (по метрикам и по словам клиентов).
          {hasTier3 && " • Дополнительные паттерны от LLM Tier 3 анализа."}
        </p>
        {hasTier3 && (
          <div className="mt-2 flex items-center gap-2 text-xs text-[var(--color-accent)]">
            <Brain size={14} />
            <span>Доступны расширенные инсайты: временные паттерны, кластеры отказов, сигналы конверсии</span>
          </div>
        )}
      </header>

      {/* Research lens */}
      <Card
        title="Тематика исследования"
        subtitle="Что мы ищем и на что ориентируемся — этот промпт LLM применяет к транскриптам"
        action={
          <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium ${isLLM ? "bandbg-good" : "bandbg-ok"}`}>
            {isLLM ? <><Sparkles size={11} /> LLM</> : <><ShieldHalf size={11} /> по ключевым словам</>}
          </span>
        }
      >
        <textarea
          value={promptValue}
          onChange={(e) => setLens(e.target.value)}
          rows={3}
          className="w-full rounded-[var(--radius-md)] border border-[var(--color-border)] bg-[var(--color-bg-card-hover)] p-3 text-sm leading-relaxed text-[var(--color-ink-secondary)] focus:outline-none focus:border-[var(--color-accent)] resize-none"
        />
        <p className="mt-2 text-[11px] text-[var(--color-ink-muted)]">
          {data.note} Чтобы применить новую тематику с LLM — задайте её в <code>.env</code> (CUSTDEV_PROMPT) и пересоберите пайплайн.
          Ниже можно вживую отфильтровать цитаты по своим ключевым словам.
        </p>
      </Card>

      {/* Live quote filter */}
      <div className="relative max-w-md">
        <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-[var(--color-ink-muted)]" />
        <input
          placeholder="Фильтр цитат по словам: цена, интеграция, crm…"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          className="w-full pl-9 pr-3 py-2 rounded-[var(--radius-md)] border border-[var(--color-border)] bg-[var(--color-bg-card)] text-sm focus:outline-none focus:border-[var(--color-accent)]"
        />
      </div>

      {/* What we heard (summary) */}
      <Card title="Что мы важное услышали" subtitle={`По ${data.total_conversations.toLocaleString("ru-RU")} реальным разговорам`}>
        <div className="space-y-2.5">
          {data.summary.map((s, i) => (
            <div key={i} className="flex items-start gap-2.5">
              <Lightbulb size={15} className="mt-0.5 shrink-0 text-[var(--color-secondary)]" />
              <p className="text-sm text-[var(--color-ink-secondary)]">
                <b className="text-[var(--color-ink)]">{s.theme}</b> <span className="stat-num text-[var(--color-ink-tertiary)]">({s.count})</span>
                {" — "}{s.recommendation}
              </p>
            </div>
          ))}
        </div>
      </Card>

      {/* Tier 3 Insights — when available */}
      {hasTier3 && (
        <section className="space-y-4">
          <h2 className="text-sm font-medium text-[var(--color-ink-tertiary)] uppercase tracking-wide flex items-center gap-2">
            <Brain size={16} />
            LLM Tier 3 — кросс-анализ звонков
          </h2>

          {/* Temporal Patterns */}
          {hasTemporal && (
            <Card
              title="Временные паттерны"
              subtitle="Зависимость успеха от времени звонка"
              icon={<Clock size={16} className="text-[var(--color-secondary)]" />}
            >
              <div className="space-y-2">
                {research.temporal.patterns.slice(0, 3).map((p: any, i: number) => (
                  <div key={i} className="rounded-md bg-[var(--color-bg-card-hover)] p-2 text-xs">
                    <div className="flex justify-between items-center mb-1">
                      <span className="font-medium">{p.time_window}</span>
                      <Badge className="bandbg-good">
                        {(p.metrics.meeting_rate * 100).toFixed(0)}% встреч
                      </Badge>
                    </div>
                    <p className="text-[var(--color-ink-tertiary)]">{p.characteristics}</p>
                    <p className="mt-1 text-[var(--color-accent)]">{p.recommendation}</p>
                  </div>
                ))}
              </div>
            </Card>
          )}

          {/* Failure Clustering */}
          {hasFailures && (
            <Card
              title="Кластеры отказов"
              subtitle="Типичные сценарии потери клиента"
              icon={<AlertTriangle size={16} className="text-[var(--color-warning)]" />}
            >
              <div className="space-y-2">
                {research.failure_clusters.clusters.slice(0, 3).map((cluster: any, i: number) => (
                  <div key={i} className="rounded-md bg-[var(--color-warning-subtle)] p-2 text-xs">
                    <div className="flex justify-between items-center mb-1">
                      <span className="font-medium">{cluster.name}</span>
                      <Badge className="bandbg-warning">
                        {(cluster.pct_of_failed * 100).toFixed(0)}%
                      </Badge>
                    </div>
                    <p className="text-[var(--color-ink-tertiary)]">{cluster.characteristics}</p>
                    <p className="mt-1 text-[var(--color-accent)]">{cluster.prompt_fix_suggestion}</p>
                  </div>
                ))}
              </div>
            </Card>
          )}

          {/* Conversion Signals */}
          {hasSignals && (
            <Card
              title="Сигналы конверсии"
              subtitle="Что предсказывает успешную встречу"
              icon={<Zap size={16} className="text-[var(--color-success)]" />}
            >
              <div className="grid grid-cols-2 gap-2">
                <div className="rounded-md bg-[var(--color-success-subtle)] p-2">
                  <p className="text-[11px] text-[var(--color-ink-muted)] mb-1">Сильные сигналы</p>
                  {research.conversion_signals.strong_signals.slice(0, 2).map((s: any, i: number) => (
                    <div key={i} className="text-xs mb-1">
                      <span className="font-medium">• {s.signal}</span>
                      <span className="text-[var(--color-success)] ml-1">{s.lift}</span>
                    </div>
                  ))}
                </div>
                <div className="rounded-md bg-[var(--color-warning-subtle)] p-2">
                  <p className="text-[11px] text-[var(--color-ink-muted)] mb-1">Негативные сигналы</p>
                  {research.conversion_signals.negative_predictors.slice(0, 2).map((s: any, i: number) => (
                    <div key={i} className="text-xs mb-1">
                      <span className="font-medium">• {s.signal}</span>
                      <span className="text-[var(--color-warning)] ml-1">{s.lift}</span>
                    </div>
                  ))}
                </div>
              </div>
            </Card>
          )}
        </section>
      )}

      {/* Insight clusters */}
      <section className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {visibleCats.map((c) => <ClusterCard key={c.key} c={c} />)}
      </section>
    </div>
  );
}

function ClusterCard({ c }: { c: CustDevCategory }) {
  return (
    <Card title={c.label} subtitle={`${c.count} упоминаний`}>
      <div className="rounded-[var(--radius-md)] bandbg-ok px-3 py-2 mb-3 text-xs">
        <b>Рекомендация:</b> {c.recommendation}
      </div>
      {c.quotes.length === 0 ? (
        <p className="text-xs text-[var(--color-ink-tertiary)]">Нет цитат по текущему фильтру.</p>
      ) : (
        <div className="space-y-1.5 max-h-64 overflow-y-auto pr-1">
          {c.quotes.map((q, i) => (
            <blockquote key={i} className="flex items-start gap-1.5 text-xs text-[var(--color-ink-secondary)] border-l-2 border-[var(--color-accent-subtle)] pl-2 py-0.5">
              <Quote size={11} className="mt-0.5 shrink-0 text-[var(--color-ink-muted)]" />
              <span>«{q.quote}» <Badge className="ml-1">{q.call_id}</Badge></span>
            </blockquote>
          ))}
        </div>
      )}
    </Card>
  );
}
