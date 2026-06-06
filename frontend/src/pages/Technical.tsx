import { useDashboardTuned } from "../hooks";
import Card from "../components/Card";
import Skeleton from "../components/Skeleton";
import { StatRow } from "../components/Stat";
import { Lock, Database, AlertCircle } from "lucide-react";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer } from "recharts";

export default function Technical() {
  // Tuned hook so threshold overrides re-band these metrics identically to VoiceAgent.
  const { data, loading } = useDashboardTuned();
  if (loading || !data)
    return <div className="p-8 space-y-4"><Skeleton h={40} w={320} /><Skeleton h={300} /></div>;

  const { quality, duration_distribution, instrumentation_spec, meta } = data;
  // technical-flavoured metrics we DO compute from the transcript
  const techMetrics = quality.metrics.filter((m) =>
    ["asr_breakdown_rate", "repair_rate", "bot_talk_share", "responsiveness"].includes(m.id));

  return (
    <div className="p-8 pt-5 space-y-7 max-w-[1280px]">
      <header>
        <h1 className="text-2xl" style={{ fontFamily: "var(--font-display)" }}>Технические метрики</h1>
        <p className="mt-1 text-sm text-[var(--color-ink-tertiary)]">
          Связь, ASR и инструментовка. Контекстный слой: эти проблемы чинит телефония/ASR, а не промпт.
        </p>
      </header>

      {/* What we have from text */}
      <section className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <Card title="Считаем из текста сейчас" subtitle="Прокси-сигналы, доступные без аудио">
          <div>{techMetrics.map((m) => <StatRow key={m.id} m={m} />)}</div>
        </Card>
        <Card title="Длительность разговоров" subtitle="Распределение, сек (состоявшиеся диалоги)">
          <div className="h-[210px]">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={duration_distribution} margin={{ left: -10, right: 10 }}>
                <XAxis dataKey="bucket_sec" tick={{ fontSize: 10, fill: "var(--color-ink-tertiary)" }} />
                <YAxis tick={{ fontSize: 10, fill: "var(--color-ink-tertiary)" }} />
                <Tooltip contentStyle={{ background: "var(--color-bg-card)", border: "1px solid var(--color-border)", borderRadius: 8, fontSize: 12 }} />
                <Bar dataKey="count" fill="var(--color-accent)" radius={[3, 3, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Card>
      </section>

      {/* What needs extraction from audio */}
      <section>
        <div className="mb-3 flex items-center gap-2">
          <Lock size={15} className="text-[var(--color-secondary)]" />
          <h2 className="text-base font-medium text-[var(--color-ink)]" style={{ fontFamily: "var(--font-display)" }}>
            Нужно извлечь из аудиозаписи звонка
          </h2>
        </div>
        <p className="mb-4 max-w-3xl text-sm text-[var(--color-ink-tertiary)]">
          Эти метрики критичны для голосового агента, но НЕ выводятся из текстовой расшифровки.
          Чтобы их получить, нужно обновить контракт данных у источника (пер-реплик таймстемпы,
          флаги перебиваний, ASR-confidence, аудио-фичи). Ниже — что нужно и зачем.
        </p>
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {instrumentation_spec.map((item) => (
            <div key={item.id} className="relative rounded-[var(--radius-xl)] border border-dashed border-[var(--color-border-strong)] bg-[var(--color-bg-card)] p-5">
              <div className="flex items-center gap-2 mb-2">
                <Lock size={14} className="text-[var(--color-ink-muted)]" />
                <span className="text-sm font-medium text-[var(--color-ink)]">{item.name}</span>
              </div>
              <p className="text-[11px] leading-relaxed text-[var(--color-ink-secondary)] mb-2">
                <b className="text-[var(--color-ink)]">Нужно:</b> {item.needs}
              </p>
              <p className="text-[11px] leading-relaxed text-[var(--color-ink-tertiary)] mb-2">
                <b className="text-[var(--color-ink-secondary)]">Зачем:</b> {item.why}
              </p>
              <p className="text-[11px] leading-relaxed text-[var(--color-accent)]">
                <b>Разблокирует:</b> {item.unlocks}
              </p>
            </div>
          ))}
        </div>
      </section>

      {/* Data quality */}
      {meta.data_quality.length > 0 && (
        <Card title="Качество данных" subtitle="Аномалии, замеченные при профилировании">
          <div className="space-y-1.5">
            {meta.data_quality.map((a, i) => (
              <div key={i} className="flex items-start gap-2 text-sm text-[var(--color-ink-secondary)]">
                <AlertCircle size={14} className="mt-0.5 shrink-0 text-[var(--color-warning)]" />
                {a}
              </div>
            ))}
          </div>
        </Card>
      )}

      <div className="flex items-center gap-2 text-xs text-[var(--color-ink-muted)]">
        <Database size={13} /> Источник: {meta.source} · сгенерировано {meta.generated_at}
      </div>
    </div>
  );
}
