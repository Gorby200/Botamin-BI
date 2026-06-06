import { useDashboardTuned, stageColor } from "../hooks";
import Card from "../components/Card";
import Skeleton from "../components/Skeleton";
import { StatCard, StatRow } from "../components/Stat";
import { fmtValue, pct } from "../format";
import { Target, PhoneCall, TrendingDown } from "lucide-react";
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell,
} from "recharts";

export default function Overview() {
  const { data, loading, error } = useDashboardTuned();

  if (error)
    return (
      <div className="p-8">
        <Card title="Ошибка загрузки данных">
          <p className="text-sm text-[var(--color-ink-secondary)]">{error}</p>
          <p className="mt-1 text-xs text-[var(--color-ink-tertiary)]">
            Запустите пайплайн: <code>python -m pipeline --file data/raw.csv</code>
          </p>
        </Card>
      </div>
    );
  if (loading || !data)
    return (
      <div className="p-8 space-y-6">
        <Skeleton h={140} />
        <div className="grid grid-cols-3 gap-4"><Skeleton h={120} /><Skeleton h={120} /><Skeleton h={120} /></div>
      </div>
    );

  const { nsm, reach, funnel, guardrails, loss_attribution: loss, bottleneck } = data;

  const funnelData = funnel.map((f) => ({ name: f.label, stage: f.stage, count: f.count }));
  const ctxShare = loss.context_share;

  return (
    <div className="p-8 pt-5 space-y-7 max-w-[1280px]">
      <header>
        <h1 className="text-2xl" style={{ fontFamily: "var(--font-display)" }}>Продукт · общая картина</h1>
        <p className="mt-1 text-sm text-[var(--color-ink-tertiary)]">
          Куда движется кампания, где теряем клиента и куда направить усилия.
        </p>
      </header>

      {/* NSM hero */}
      <section className="grid grid-cols-1 lg:grid-cols-[1.3fr_1fr] gap-4">
        <div className="rounded-[var(--radius-xl)] border border-[var(--color-border)] bg-[var(--color-bg-card)] p-6 relative overflow-hidden">
          <div className="absolute inset-0 opacity-[0.05] pointer-events-none"
               style={{ background: "radial-gradient(ellipse at 25% 15%, var(--color-accent) 0%, transparent 65%)" }} />
          <div className="relative">
            <div className="flex items-center gap-2 mb-1">
              <Target size={16} className="text-[var(--color-accent)]" />
              <span className="text-[11px] font-medium uppercase tracking-wider text-[var(--color-ink-tertiary)]">
                Северная звезда · {nsm.name}
              </span>
            </div>
            <div className="flex items-end gap-3">
              <span className={`stat-num text-[3.5rem] leading-none ${nsm.band === "bad" ? "band-bad" : nsm.band === "ok" ? "band-ok" : "band-good"}`}>
                {fmtValue(nsm.value, nsm.fmt)}
              </span>
              <span className="mb-2 text-sm text-[var(--color-ink-tertiary)]">
                {nsm.counts.qualified} квал. встреч / {nsm.counts.consent} согласий
              </span>
            </div>
            <p className="mt-3 max-w-xl text-sm leading-relaxed text-[var(--color-ink-secondary)]">{nsm.comment}</p>
            <p className="mt-1 max-w-xl text-xs leading-relaxed text-[var(--color-ink-tertiary)]">{nsm.why}</p>
          </div>
        </div>

        {/* NSM variants */}
        <Card title="Как ещё смотреть на цель" subtitle="Один QMR не покрывает всё — вот честные варианты">
          <div className="space-y-2.5">
            {Object.entries(nsm.variants).map(([k, v]) => (
              <div key={k} className="flex items-center justify-between gap-3">
                <div className="min-w-0">
                  <span className="text-sm text-[var(--color-ink)]">{v.label}</span>
                  <p className="text-[11px] text-[var(--color-ink-tertiary)] leading-snug">{v.hint}</p>
                </div>
                <span className="stat-num text-lg text-[var(--color-ink-secondary)] shrink-0">{pct(v.value)}</span>
              </div>
            ))}
          </div>
        </Card>
      </section>

      {/* Reach */}
      <section>
        <SectionLabel icon={<PhoneCall size={14} />} title="Дозвон и вовлечение" hint="Контекстный слой: качество базы и связи, НЕ промпт" />
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {reach.metrics.map((m) => <StatCard key={m.id} m={m} />)}
        </div>
      </section>

      {/* Loss attribution + funnel */}
      <section className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <Card title="Куда уходят клиенты" subtitle="Контекст (связь) vs Управляемое (промпт) — чиним только второе">
          <div className="mb-4">
            <div className="flex h-7 w-full overflow-hidden rounded-[var(--radius-sm)]">
              <div className="flex items-center justify-center text-[11px] font-medium text-white"
                   style={{ width: `${ctxShare * 100}%`, background: "var(--color-band-ok)" }}>
                {ctxShare >= 0.08 && `Контекст ${pct(ctxShare, 0)}`}
              </div>
              <div className="flex items-center justify-center text-[11px] font-medium text-white"
                   style={{ width: `${loss.controllable_share * 100}%`, background: "var(--color-accent)" }}>
                Управляемое {pct(loss.controllable_share, 0)}
              </div>
            </div>
          </div>
          <div className="space-y-1.5">
            {loss.by_reason.slice(0, 6).map((r) => (
              <div key={r.reason} className="flex items-center justify-between text-sm">
                <span className="text-[var(--color-ink-secondary)]">{r.label}</span>
                <span className="stat-num text-sm text-[var(--color-ink-tertiary)]">{r.count.toLocaleString("ru-RU")}</span>
              </div>
            ))}
          </div>
        </Card>

        <Card title="Воронка" subtitle="Состоявшиеся разговоры по стадиям">
          <div className="h-[230px]">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={funnelData} layout="vertical" margin={{ left: 8, right: 40 }}>
                <XAxis type="number" hide />
                <YAxis dataKey="name" type="category" width={92} tick={{ fontSize: 12, fill: "var(--color-ink-secondary)" }} />
                <Tooltip
                  contentStyle={{ background: "var(--color-bg-card)", border: "1px solid var(--color-border)", borderRadius: 8, fontSize: 12 }}
                  formatter={(v: any) => [Number(v).toLocaleString("ru-RU"), "Дошли"]}
                />
                <Bar dataKey="count" radius={[0, 6, 6, 0]} barSize={26} label={{ position: "right", fontSize: 11, fill: "var(--color-ink-tertiary)" }}>
                  {funnelData.map((d) => <Cell key={d.stage} fill={stageColor(d.stage)} />)}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Card>
      </section>

      {/* Bottleneck callout */}
      <section className="rounded-[var(--radius-xl)] border border-[var(--color-band-bad)]/25 bandbg-bad p-5">
        <div className="flex items-start gap-3">
          <TrendingDown size={20} className="mt-0.5 shrink-0" />
          <div>
            <h3 className="text-base font-medium" style={{ fontFamily: "var(--font-display)" }}>
              Узкое место: {bottleneck.label} — {pct(bottleneck.conversion)}
            </h3>
            <p className="mt-1 text-sm text-[var(--color-ink-secondary)]">
              Здесь теряется больше всего клиентов: {bottleneck.dropped_abs.toLocaleString("ru-RU")} чел.
              Блок промпта: <b>{bottleneck.prompt_block}</b>. {bottleneck.rationale}
            </p>
          </div>
        </div>
      </section>

      {/* Guardrails */}
      <section>
        <Card title="Guardrails" subtitle="Метрики-ограничители: что нельзя сломать, двигая конверсию">
          <div>{guardrails.map((g) => <StatRow key={g.id} m={g} />)}</div>
        </Card>
      </section>
    </div>
  );
}

function SectionLabel({ icon, title, hint }: { icon: React.ReactNode; title: string; hint: string }) {
  return (
    <div className="mb-3 flex items-center gap-2">
      <span className="text-[var(--color-accent)]">{icon}</span>
      <h2 className="text-sm font-medium uppercase tracking-wider text-[var(--color-ink-secondary)]">{title}</h2>
      <span className="text-xs text-[var(--color-ink-muted)]">· {hint}</span>
    </div>
  );
}
