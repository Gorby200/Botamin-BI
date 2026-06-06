import { useBacklog } from "../hooks";
import Card from "../components/Card";
import Badge from "../components/Badge";
import Skeleton from "../components/Skeleton";
import { FlaskConical, Shield, TrendingUp } from "lucide-react";
import type { BacklogItem } from "../types";

const BLOCK_LABELS: Record<string, string> = {
  opener: "Опенер", offer: "Оффер", closing: "Закрытие/CTA",
  qualification: "Квалификация", context: "Контекст (связь/ASR)",
};
const EFFORT: Record<string, { label: string; variant: "positive" | "warning" | "negative" }> = {
  low: { label: "Низкий", variant: "positive" },
  med: { label: "Средний", variant: "warning" },
  high: { label: "Высокий", variant: "negative" },
};

export default function Backlog() {
  const { data: backlog, loading } = useBacklog();
  if (loading || !backlog) return <div className="p-8"><Skeleton h={400} /></div>;

  return (
    <div className="p-8 pt-5 space-y-6 max-w-[1100px]">
      <header>
        <h1 className="text-2xl" style={{ fontFamily: "var(--font-display)" }}>Бэклог гипотез коррекций</h1>
        <p className="mt-1 text-sm text-[var(--color-ink-tertiary)]">
          Ранжирование по ROI: ожидаемый рост NSM с учётом усилия и прохождения вниз по воронке.
          Это движок цикла «измерил → диагностировал → поправил → проверил A/B».
        </p>
      </header>

      <div className="space-y-4">
        {backlog.map((h) => <HypothesisCard key={h.priority} h={h} />)}
      </div>
    </div>
  );
}

function HypothesisCard({ h }: { h: BacklogItem }) {
  const eff = EFFORT[h.effort] || EFFORT.med;
  const isContext = h.prompt_block === "context";
  return (
    <Card title={`#${h.priority} · ${BLOCK_LABELS[h.prompt_block] || h.prompt_block}`} subtitle={`Стадия: ${h.stage}`}>
      <div className="grid grid-cols-1 lg:grid-cols-[1.5fr_1fr] gap-5">
        {/* Left: hypothesis + evidence */}
        <div className="space-y-3">
          <p className="text-sm font-medium text-[var(--color-ink)]">{h.hypothesis}</p>
          {h.alternatives.length > 0 && (
            <ul className="list-disc pl-5 space-y-0.5">
              {h.alternatives.map((a, i) => (
                <li key={i} className="text-xs text-[var(--color-ink-tertiary)]">{a}</li>
              ))}
            </ul>
          )}

          <div className="rounded-[var(--radius-md)] bg-[var(--color-bg-card-hover)] p-3 space-y-2">
            <p className="text-[10px] font-medium uppercase tracking-wider text-[var(--color-ink-tertiary)]">Доказательная база</p>
            <div className="text-sm text-[var(--color-ink-secondary)]">
              Метрика <span className="stat-num">{h.evidence.metric}</span> = <span className="stat-num">{(h.evidence.value * 100).toFixed(1)}%</span>
            </div>
            {h.evidence.note && <p className="text-xs text-[var(--color-ink-tertiary)]">{h.evidence.note}</p>}
            {h.evidence.patterns.slice(0, 3).map((p, i) => (
              <div key={i} className="text-xs text-[var(--color-ink-tertiary)]">• {p}</div>
            ))}
            {h.evidence.verbatims.slice(0, 2).map((v, i) => (
              <blockquote key={i} className="text-xs italic text-[var(--color-ink-tertiary)] border-l-2 border-[var(--color-accent-subtle)] pl-2">
                «{v.slice(0, 130)}»
              </blockquote>
            ))}
          </div>

          {h.risk_guardrails.length > 0 && (
            <div className="flex items-center gap-2 flex-wrap">
              <Shield size={12} className="text-[var(--color-warning)]" />
              <span className="text-xs text-[var(--color-ink-tertiary)]">Не сломать:</span>
              {h.risk_guardrails.map((g) => <Badge key={g} variant="warning">{g}</Badge>)}
            </div>
          )}
        </div>

        {/* Right: impact + A/B */}
        <div className="space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <Metric label="Δ драйвер" value={`+${h.expected_driver_delta_pp.toFixed(1)}pp`} />
            <Metric label="Δ NSM" value={isContext ? "—" : `+${h.expected_nsm_delta_pp.toFixed(2)}pp`} accent />
          </div>
          <Row label="Прохождение вниз" value={`${(h.downstream_pass_through * 100).toFixed(1)}%`} />
          <Row label="Усилие" value={<Badge variant={eff.variant}>{eff.label}</Badge>} />
          <Row label="Уверенность" value={`${(h.confidence * 100).toFixed(0)}%`} />

          {!isContext && (
            <div className="rounded-[var(--radius-md)] border border-[var(--color-border)] p-3 space-y-1.5">
              <p className="flex items-center gap-1.5 text-[10px] font-medium uppercase tracking-wider text-[var(--color-ink-tertiary)]">
                <FlaskConical size={11} /> Дизайн A/B
              </p>
              <Row small label="Primary" value={h.ab_design.primary} />
              <Row small label="MDE" value={`±${h.ab_design.mde_pp}pp`} />
              <Row small label="Выборка/ветка" value={h.ab_design.sample.toLocaleString("ru-RU")} />
            </div>
          )}
        </div>
      </div>
    </Card>
  );
}

function Metric({ label, value, accent }: { label: string; value: string; accent?: boolean }) {
  return (
    <div className={`rounded-[var(--radius-lg)] p-3 text-center ${accent ? "bg-[var(--color-accent-bg)]" : "bg-[var(--color-bg-card-hover)]"}`}>
      <div className={`text-[10px] uppercase tracking-wider mb-1 ${accent ? "text-[var(--color-accent)]" : "text-[var(--color-ink-tertiary)]"}`}>{label}</div>
      <div className={`stat-num text-xl ${accent ? "text-[var(--color-accent)]" : "text-[var(--color-ink)]"} flex items-center justify-center gap-1`}>
        {accent && <TrendingUp size={15} />}{value}
      </div>
    </div>
  );
}

function Row({ label, value, small }: { label: string; value: React.ReactNode; small?: boolean }) {
  return (
    <div className={`flex items-center justify-between ${small ? "text-xs" : "text-sm"} ${small ? "" : "py-1.5 border-b border-[var(--color-border)] last:border-0"}`}>
      <span className="text-[var(--color-ink-tertiary)]">{label}</span>
      <span className="text-[var(--color-ink-secondary)] tabular-nums">{value}</span>
    </div>
  );
}
