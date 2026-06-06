import { useDashboardTuned } from "../hooks";
import Card from "../components/Card";
import Skeleton from "../components/Skeleton";
import { StatCard } from "../components/Stat";
import Badge from "../components/Badge";
import { pct } from "../format";
import { ThumbsUp, ThumbsDown, Wrench } from "lucide-react";
import type { GapAnalysis } from "../types";

export default function VoiceAgent() {
  const { data, loading } = useDashboardTuned();
  if (loading || !data)
    return <div className="p-8 space-y-4"><Skeleton h={40} w={320} /><div className="grid grid-cols-3 gap-4"><Skeleton h={120} /><Skeleton h={120} /><Skeleton h={120} /></div></div>;

  const { quality, diagnostics, meta } = data;
  const isDet = !String(meta.llm.mode || "").startsWith("llm");
  const gap = data.gap_analysis;
  const negatives = diagnostics.pattern_audit.filter((p) => p.polarity === "negative");
  const positives = diagnostics.pattern_audit.filter((p) => p.polarity === "positive");

  // Dynamic recommendations: bad/ok quality metrics + frequent negative patterns
  const recs: { text: string; tag: string }[] = [];
  quality.metrics.filter((m) => m.band !== "good").forEach((m) =>
    recs.push({ text: m.comment, tag: m.name }));
  negatives.filter((p) => p.share >= 0.1).slice(0, 3).forEach((p) =>
    recs.push({ text: `Паттерн «${p.name}» в ${pct(p.share, 2)} разговоров (lift ${p.lift_on_advance >= 0 ? "+" : ""}${(p.lift_on_advance * 100).toFixed(0)}pp к продвижению). Снизить частоту.`, tag: p.psy_id }));

  return (
    <div className="p-8 pt-5 space-y-7 max-w-[1280px]">
      <header>
        <h1 className="text-2xl" style={{ fontFamily: "var(--font-display)" }}>Эффективность голосового агента</h1>
        <p className="mt-1 text-sm text-[var(--color-ink-tertiary)]">
          Качество ведения диалога + паттерны поведения бота + что подкрутить. Микс продуктовых и технических сигналов.
        </p>
      </header>

      {isDet && (
        <div className="rounded-[var(--radius-md)] bandbg-ok px-4 py-2.5 text-xs">
          Отзывчивость и качество посчитаны прокси-эвристикой (LLM выключена). С ключом в <code>.env</code> эти метрики станут точными.
        </div>
      )}

      <section>
        <h2 className="mb-3 text-base font-medium text-[var(--color-ink)]" style={{ fontFamily: "var(--font-display)" }}>Качество диалога</h2>
        <div className="grid grid-cols-1 md:grid-cols-3 xl:grid-cols-5 gap-4">
          {quality.metrics.map((m) => <StatCard key={m.id} m={m} />)}
        </div>
      </section>

      {/* V4 quality + gap analysis (LLM judges layers; pipeline computes the numbers) */}
      {gap && <QualityGapCard g={gap} />}

      {/* Recommendations */}
      <Card title="Что подкрутить" subtitle="Авто-рекомендации из метрик и паттернов (детали и приоритет — в Бэклоге)">
        <div className="space-y-2.5">
          {recs.length === 0 && <p className="text-sm text-[var(--color-ink-tertiary)]">Все метрики в норме — критичных правок не выявлено.</p>}
          {recs.map((r, i) => (
            <div key={i} className="flex items-start gap-2.5">
              <Wrench size={14} className="mt-0.5 shrink-0 text-[var(--color-accent)]" />
              <p className="text-sm text-[var(--color-ink-secondary)] leading-snug">
                {r.text} <Badge variant="accent" className="ml-1">{r.tag}</Badge>
              </p>
            </div>
          ))}
        </div>
      </Card>

      {/* Patterns */}
      <section className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <Card title="Вредные паттерны" subtitle="Поведение бота, мешающее продвижению">
          <div className="space-y-2">
            {negatives.length === 0 && <p className="text-sm text-[var(--color-ink-tertiary)]">Не обнаружено.</p>}
            {negatives.slice(0, 7).map((p) => <PatternRow key={p.psy_id} p={p} bad />)}
          </div>
        </Card>
        <Card title="Полезные паттерны" subtitle="Что бот делает правильно">
          <div className="space-y-2">
            {positives.length === 0 && <p className="text-sm text-[var(--color-ink-tertiary)]">Не обнаружено.</p>}
            {positives.slice(0, 7).map((p) => <PatternRow key={p.psy_id} p={p} />)}
          </div>
        </Card>
      </section>

      {/* Pitch */}
      <section className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <Card title="Что заходит в питче" subtitle="Фразы бота, чаще встречающиеся в продвинувшихся диалогах">
          <PhraseList items={diagnostics.pitch.resonated.map((r) => ({ phrase: r.phrase, a: r.stayed, b: r.left }))} good />
        </Card>
        <Card title="Что не заходит" subtitle="Фразы, чаще встречающиеся там, где клиент отвалился">
          <PhraseList items={diagnostics.pitch.fell_flat.map((r) => ({ phrase: r.phrase, a: r.left, b: r.stayed }))} />
        </Card>
      </section>
    </div>
  );
}

function QualityGapCard({ g }: { g: GapAnalysis }) {
  const gapBand = g.avg_gap > 1.5 ? "band-bad" : g.avg_gap < -1.5 ? "" : "band-good";
  const gapSign = g.avg_gap >= 0 ? "+" : "";
  return (
    <Card
      title="Качество ведения (V4) и Gap-анализ"
      subtitle={`Качество слоёв судит LLM, итог/грейд/разрыв считает пайплайн · по ${g.n.toLocaleString("ru-RU")} разговорам`}
    >
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
        <GapStat label="Качество ведения" value={`${g.avg_quality.toFixed(1)}/10`} hint="как ведёт бот (LLM)" />
        <GapStat label="Результат (outcome)" value={`${g.avg_outcome.toFixed(1)}/10`} hint="как далеко дошёл клиент" />
        <GapStat label="Разрыв (gap)" value={`${gapSign}${g.avg_gap.toFixed(1)}`} cls={gapBand} hint="качество − результат" />
        <GapStat label="Разговоров" value={g.n.toLocaleString("ru-RU")} hint="connected" />
      </div>
      <div className="flex flex-wrap items-center gap-1.5 mb-3">
        {g.grade_distribution.map((gd) => (
          <Badge key={gd.grade}>{gd.grade}: {gd.count}</Badge>
        ))}
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-2 mb-3 text-xs">
        <div className="rounded-md bandbg-bad px-2.5 py-1.5">Узкое место в закрытии/базе: <b className="stat-num">{g.buckets.closing_bottleneck}</b></div>
        <div className="rounded-md bandbg-ok px-2.5 py-1.5">Тёплая база (доходят «вопреки»): <b className="stat-num">{g.buckets.warm_base}</b></div>
        <div className="rounded-md bandbg-good px-2.5 py-1.5">Качество = результат: <b className="stat-num">{g.buckets.aligned}</b></div>
      </div>
      <p className="text-sm text-[var(--color-ink-secondary)] leading-snug">{g.interpretation}</p>
    </Card>
  );
}

function GapStat({ label, value, hint, cls }: { label: string; value: string; hint?: string; cls?: string }) {
  return (
    <div>
      <div className="text-[11px] uppercase tracking-wide text-[var(--color-ink-muted)]">{label}</div>
      <div className={`stat-num text-2xl ${cls || "text-[var(--color-ink)]"}`}>{value}</div>
      {hint && <div className="text-[11px] text-[var(--color-ink-tertiary)]">{hint}</div>}
    </div>
  );
}

function PatternRow({ p, bad }: { p: { psy_id: string; name: string; share: number; lift_on_advance: number; impact: string; category?: string }; bad?: boolean }) {
  return (
    <div className="flex items-center justify-between gap-2 text-sm">
      <div className="flex items-center gap-2 min-w-0">
        {bad ? <ThumbsDown size={13} className="text-[var(--color-band-bad)] shrink-0" /> : <ThumbsUp size={13} className="text-[var(--color-band-good)] shrink-0" />}
        <Badge variant={bad ? "negative" : "positive"}>{p.psy_id}</Badge>
        <span className="truncate text-[var(--color-ink-secondary)]">{p.name}</span>
        {p.category && <span className="hidden lg:inline text-[10px] text-[var(--color-ink-muted)] shrink-0">· {p.category}</span>}
      </div>
      <div className="flex items-center gap-3 shrink-0">
        <span className="stat-num text-xs text-[var(--color-ink-tertiary)]">{pct(p.share, 2)}</span>
        <span className={`stat-num text-xs ${p.lift_on_advance >= 0 ? "band-good" : "band-bad"}`}>
          {p.lift_on_advance >= 0 ? "+" : ""}{(p.lift_on_advance * 100).toFixed(0)}pp
        </span>
      </div>
    </div>
  );
}

function PhraseList({ items, good }: { items: { phrase: string; a: number; b: number }[]; good?: boolean }) {
  if (items.length === 0) return <p className="text-sm text-[var(--color-ink-tertiary)]">Недостаточно данных.</p>;
  return (
    <div className="space-y-2">
      {items.map((it, i) => (
        <blockquote key={i} className={`text-xs leading-snug border-l-2 pl-2.5 py-0.5 ${good ? "border-[var(--color-band-good)]" : "border-[var(--color-band-bad)]"} text-[var(--color-ink-secondary)]`}>
          «{it.phrase}» <span className="text-[var(--color-ink-muted)] tabular-nums">({it.a}↑ / {it.b}↓)</span>
        </blockquote>
      ))}
    </div>
  );
}
