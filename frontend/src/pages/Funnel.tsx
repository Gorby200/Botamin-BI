import { useDashboardTuned, stageColor } from "../hooks";
import Card from "../components/Card";
import Skeleton from "../components/Skeleton";
import { StatCard } from "../components/Stat";
import { pct } from "../format";
import type { Driver } from "../types";

const BLOCK_LABEL: Record<string, string> = {
  opener: "Опенер", offer: "Оффер", closing: "Закрытие", qualification: "Квалификация",
};

export default function Funnel() {
  const { data, loading } = useDashboardTuned();
  if (loading || !data)
    return <div className="p-8 space-y-4"><Skeleton h={40} w={280} /><Skeleton h={300} /></div>;

  const { funnel, drivers, bottleneck, reach } = data;
  const maxCount = Math.max(...funnel.map((f) => f.count), 1);

  return (
    <div className="p-8 pt-5 space-y-7 max-w-[1280px]">
      <header>
        <h1 className="text-2xl" style={{ fontFamily: "var(--font-display)" }}>Воронка S0 → S4</h1>
        <p className="mt-1 text-sm text-[var(--color-ink-tertiary)]">
          Каждая стадия засчитывается ТОЛЬКО по словам клиента, а не по действиям бота.
          База — {reach.engaged.toLocaleString("ru-RU")} состоявшихся разговоров.
        </p>
      </header>

      <Card title="Стадии диалога" subtitle="Что должен подтвердить клиент на каждом шаге">
        <div className="space-y-3">
          {funnel.map((f, i) => {
            const w = (f.count / maxCount) * 100;
            const prev = i > 0 ? funnel[i - 1] : null;
            return (
              <div key={f.stage}>
                <div className="flex items-center gap-3">
                  <span className="w-28 shrink-0 text-sm text-[var(--color-ink-secondary)]">
                    <span className="text-[var(--color-ink-muted)] mr-1">{f.stage}</span>{f.label}
                  </span>
                  <div className="relative flex-1 h-9 rounded-[var(--radius-sm)] bg-[var(--color-bg-card-hover)] overflow-hidden">
                    <div className="h-full flex items-center px-3 transition-all"
                         style={{ width: `${Math.max(w, 8)}%`, background: stageColor(f.stage) }}>
                      <span className="stat-num text-sm text-white">{f.count.toLocaleString("ru-RU")}</span>
                    </div>
                  </div>
                  <span className="w-16 shrink-0 text-right">
                    {prev && <span className="stat-num text-sm text-[var(--color-ink-secondary)]">{pct(f.conversion_from_prev)}</span>}
                  </span>
                </div>
                {prev && (f.drop_attribution.context_loss || f.drop_attribution.controllable_loss) ? (
                  <div className="mt-1 pl-[124px] text-[11px] text-[var(--color-ink-muted)]">
                    −{f.dropped_abs.toLocaleString("ru-RU")} отвал
                    {f.drop_attribution.context_loss ? ` · контекст ${f.drop_attribution.context_loss}` : ""}
                    {f.drop_attribution.controllable_loss ? ` · промпт ${f.drop_attribution.controllable_loss}` : ""}
                  </div>
                ) : null}
              </div>
            );
          })}
        </div>
      </Card>

      <div className="rounded-[var(--radius-xl)] border border-[var(--color-band-bad)]/25 bandbg-bad p-5">
        <h3 className="text-base font-medium" style={{ fontFamily: "var(--font-display)" }}>
          Узкое место: {bottleneck.label} ({pct(bottleneck.conversion)})
        </h3>
        <p className="mt-1 text-sm text-[var(--color-ink-secondary)]">
          {bottleneck.dropped_abs.toLocaleString("ru-RU")} потерянных клиентов. {bottleneck.rationale}
        </p>
      </div>

      <section>
        <h2 className="mb-3 text-sm font-medium uppercase tracking-wider text-[var(--color-ink-secondary)]">
          Драйверы — 4 переходные конверсии (= 4 блока промпта)
        </h2>
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4">
          {drivers.map((d) => <DriverCard key={d.id} d={d} />)}
        </div>
      </section>
    </div>
  );
}

function DriverCard({ d }: { d: Driver }) {
  return (
    <div className="space-y-2">
      <StatCard m={d} />
      <div className="rounded-[var(--radius-md)] border border-[var(--color-border)] bg-[var(--color-bg-card)] px-4 py-3 text-[11px] text-[var(--color-ink-tertiary)] space-y-1">
        <div className="flex justify-between"><span>Блок промпта</span><span className="text-[var(--color-ink-secondary)]">{BLOCK_LABEL[d.prompt_block] || d.prompt_block}</span></div>
        <div className="flex justify-between"><span>MDE для A/B</span><span className="stat-num">{d.mde_pp} pp</span></div>
        <div className="flex justify-between"><span>Выборка на ветку</span><span className="stat-num">{d.sample_needed.toLocaleString("ru-RU")}</span></div>
      </div>
    </div>
  );
}
