import { useDashboardTuned, useCustDev, useBacklog } from "../hooks";
import { pct, fmtDuration } from "../format";
import Skeleton from "../components/Skeleton";
import { Download, Phone, Target, TrendingDown, Award, Lightbulb, ListChecks, ThumbsUp, ThumbsDown } from "lucide-react";

/**
 * Client-facing call-analytics report, print-optimized for "Save as PDF".
 * Pulls ONLY precomputed values from the JSON contract (no client-side recompute),
 * so the report can never contradict the dashboard pages. The `no-print` controls
 * are hidden by the @media print rules in index.css; `window.print()` yields a
 * crisp, vector, selectable A4 PDF with zero extra dependencies.
 */
export default function Report() {
  const { data, loading } = useDashboardTuned();
  const { data: custdev } = useCustDev();
  const { data: backlog } = useBacklog();

  if (loading || !data)
    return <div className="p-8 space-y-4"><Skeleton h={40} w={320} /><Skeleton h={500} /></div>;

  const { meta, nsm, reach, funnel, loss_attribution: loss, bottleneck, gap_analysis: gap, diagnostics, guardrails } = data;
  const connect = reach.metrics.find((m) => m.id === "connect_rate")?.value ?? 0;
  const engageRate = reach.metrics.find((m) => m.id === "conversation_rate")?.value ?? 0;
  const meetingRate = nsm.variants?.meeting_rate?.value;
  const pos = diagnostics.pattern_audit.filter((p) => p.polarity === "positive").slice(0, 4);
  const neg = diagnostics.pattern_audit.filter((p) => p.polarity === "negative").slice(0, 4);
  const topThemes = (custdev?.summary ?? []).slice(0, 5);
  const topBacklog = [...backlog].sort((a, b) => a.priority - b.priority).slice(0, 5);
  const mode = String(meta.llm.mode || "").startsWith("llm") ? `LLM (${meta.llm.provider})` : "детерминированный";

  return (
    <div className="report-doc mx-auto max-w-[900px] p-8 pt-5 text-[var(--color-ink)]">
      {/* Toolbar (screen only) */}
      <div className="no-print mb-5 flex items-center justify-between">
        <p className="text-xs text-[var(--color-ink-tertiary)]">
          Клиентский отчёт · готов к выгрузке. Кнопка «Скачать PDF» откроет печать — выберите «Сохранить как PDF».
        </p>
        <button onClick={() => window.print()}
          className="inline-flex items-center gap-2 rounded-[var(--radius-md)] bg-[var(--color-accent)] text-white px-4 py-2 text-sm font-medium hover:opacity-90">
          <Download size={15} /> Скачать PDF
        </button>
      </div>

      {/* Cover */}
      <header className="report-block border-b-2 border-[var(--color-accent)] pb-4 mb-6">
        <div className="flex items-end justify-between">
          <div>
            <h1 className="text-3xl" style={{ fontFamily: "var(--font-display)" }}>
              Отчёт по звонкам <span className="text-[var(--color-accent)]">Botamin</span>
            </h1>
            <p className="mt-1 text-sm text-[var(--color-ink-tertiary)]">
              Анализ эффективности голосового агента продаж
            </p>
          </div>
          <div className="text-right text-xs text-[var(--color-ink-tertiary)] tabular-nums">
            {meta.period_from && meta.period_to && <div>Период: {meta.period_from} — {meta.period_to}</div>}
            <div>Звонков: {meta.total_rows.toLocaleString("ru-RU")}</div>
            <div>Сформирован: {meta.generated_at?.slice(0, 10)}</div>
            <div>Разбор: {mode}</div>
          </div>
        </div>
      </header>

      {/* 1. Executive summary */}
      <Block n="1" title="Резюме для руководителя" icon={<Target size={16} />}>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-3">
          <KPI label="NSM · QMR" value={pct(nsm.value, 2)} sub="квал. встречи / согласия" band={nsm.band} />
          <KPI label="Дозвон" value={pct(connect, 2)} sub="опенер доставлен" />
          <KPI label="Вовлечение" value={pct(engageRate, 2)} sub="холодный → тёплый" />
          <KPI label="Meeting Rate" value={meetingRate != null ? pct(meetingRate, 2) : "—"} sub="встречи / согласия" />
        </div>
        <p className="text-sm leading-relaxed text-[var(--color-ink-secondary)]">
          {nsm.verdict ? <><b>{nsm.verdict}.</b> </> : null}
          Узкое место — <b>{bottleneck?.label}</b> (конверсия {pct(bottleneck?.conversion ?? 0, 2)},
          теряем {bottleneck?.dropped_abs?.toLocaleString("ru-RU")} клиентов). Из всех потерь
          <b> {pct(loss.controllable_share, 2)} управляемы промптом</b> и {pct(loss.context_share, 2)} —
          это связь/дозвон (зона телефонии/ASR). Фокус усилий — блок «{bottleneck?.prompt_block}».
        </p>
      </Block>

      {/* 2. Funnel */}
      <Block n="2" title="Воронка S0 → S4" icon={<TrendingDown size={16} />}>
        <table className="w-full text-sm">
          <thead><tr className="text-[10px] uppercase tracking-wider text-[var(--color-ink-tertiary)] border-b border-[var(--color-border)]">
            <th className="text-left py-1.5">Стадия</th><th className="text-right py-1.5">Дошло</th>
            <th className="text-right py-1.5">Конверсия</th><th className="text-right py-1.5">Потеряно</th>
          </tr></thead>
          <tbody>
            {funnel.map((f) => (
              <tr key={f.stage} className="border-b border-[var(--color-border)]/60">
                <td className="py-1.5 font-medium">{f.stage} · {f.label}</td>
                <td className="py-1.5 text-right stat-num">{f.count.toLocaleString("ru-RU")}</td>
                <td className="py-1.5 text-right stat-num">{f.stage === "S0" ? "—" : pct(f.conversion_from_prev, 2)}</td>
                <td className="py-1.5 text-right stat-num text-[var(--color-ink-tertiary)]">{f.dropped_abs ? `−${f.dropped_abs.toLocaleString("ru-RU")}` : "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Block>

      {/* 3. Loss attribution */}
      <Block n="3" title="Куда уходят клиенты" icon={<Phone size={16} />}>
        <div className="flex h-3 w-full overflow-hidden rounded-full mb-2">
          <div className="bg-[var(--color-band-bad)]" style={{ width: `${(loss.controllable_share * 100).toFixed(1)}%` }} />
          <div className="bg-[var(--color-band-ok)]" style={{ width: `${(loss.context_share * 100).toFixed(1)}%` }} />
        </div>
        <p className="text-xs text-[var(--color-ink-secondary)] mb-2">
          <b className="band-bad">Управляемое (промпт): {pct(loss.controllable_share, 2)}</b> ·
          <b className="band-ok"> Контекст (связь): {pct(loss.context_share, 2)}</b>
        </p>
        <div className="flex flex-wrap gap-x-5 gap-y-1 text-xs text-[var(--color-ink-secondary)]">
          {loss.by_reason.slice(0, 6).map((r) => (
            <span key={r.reason}>{r.label}: <b className="stat-num">{r.count.toLocaleString("ru-RU")}</b></span>
          ))}
        </div>
      </Block>

      {/* 4. Quality V4 */}
      {gap && (
        <Block n="4" title="Качество ведения диалога (V4)" icon={<Award size={16} />}>
          <div className="grid grid-cols-3 gap-3 mb-2">
            <KPI label="Качество" value={`${gap.avg_quality.toFixed(1)}/10`} sub="как ведёт бот" />
            <KPI label="Результат" value={`${gap.avg_outcome.toFixed(1)}/10`} sub="продвижение клиента" />
            <KPI label="Разрыв" value={`${gap.avg_gap >= 0 ? "+" : ""}${gap.avg_gap.toFixed(1)}`} sub="качество − результат" />
          </div>
          <div className="flex flex-wrap gap-1.5 mb-2">
            {gap.grade_distribution.map((g) => (
              <span key={g.grade} className="rounded bg-[var(--color-bg-card-hover)] px-2 py-0.5 text-xs">Грейд {g.grade}: <b className="stat-num">{g.count}</b></span>
            ))}
          </div>
          <p className="text-sm text-[var(--color-ink-secondary)]">{gap.interpretation}</p>
        </Block>
      )}

      {/* 5. Psychology */}
      <Block n="5" title="Психологические приёмы бота" icon={<Award size={16} />}>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <PatternCol title="Работает" rows={pos} good />
          <PatternCol title="Мешает" rows={neg} />
        </div>
        <p className="mt-2 text-[11px] text-[var(--color-ink-muted)]">
          % — доля разговоров с приёмом; lift — влияние на продвижение к встрече.
        </p>
      </Block>

      {/* 6. Voice of customer */}
      {topThemes.length > 0 && (
        <Block n="6" title="Голос клиента (CustDev)" icon={<Lightbulb size={16} />}>
          <ul className="space-y-1.5 text-sm">
            {topThemes.map((t, i) => (
              <li key={i} className="text-[var(--color-ink-secondary)]">
                <b className="text-[var(--color-ink)]">{t.theme}</b> <span className="stat-num text-[var(--color-ink-tertiary)]">({t.count})</span> — {t.recommendation}
              </li>
            ))}
          </ul>
        </Block>
      )}

      {/* 7. Recommendations */}
      {topBacklog.length > 0 && (
        <Block n="7" title="Рекомендации (приоритеты)" icon={<ListChecks size={16} />}>
          <ol className="space-y-2">
            {topBacklog.map((b, i) => (
              <li key={i} className="flex items-start gap-2.5 text-sm">
                <span className="stat-num shrink-0 w-5 text-[var(--color-accent)] font-medium">#{b.priority}</span>
                <div>
                  <span className="text-[var(--color-ink-secondary)]">{b.hypothesis}</span>
                  <span className="ml-1 text-[11px] text-[var(--color-ink-muted)]">
                    [{b.prompt_block} · ΔNSM≈{b.expected_nsm_delta_pp}pp · усилие {b.effort}]
                  </span>
                </div>
              </li>
            ))}
          </ol>
        </Block>
      )}

      {/* 8. Guardrails */}
      <Block n="8" title="Контр-метрики (что нельзя сломать ради роста)" icon={<Target size={16} />}>
        <div className="flex flex-wrap gap-x-5 gap-y-1 text-sm text-[var(--color-ink-secondary)]">
          {guardrails.map((g) => (
            <span key={g.id}>{g.name}: <b className="stat-num">{g.fmt === "sec" ? fmtDuration(g.value) : g.fmt === "pct" ? pct(g.value, 2) : g.value}</b></span>
          ))}
        </div>
      </Block>

      <footer className="report-block mt-6 pt-3 border-t border-[var(--color-border)] text-[11px] leading-relaxed text-[var(--color-ink-muted)]">
        Методика: клиент-привязанная воронка S0→S4, NSM = QMR (квалифицированные встречи / согласия), бинарная атрибуция
        потерь (контекст vs управляемое), психологический разбор (адаптация боевой методики, ~66 паттернов) и оценка
        качества V4. Числа считаются детерминированно; смысловую разметку даёт LLM с дословными цитатами.
        Адаптировано с реального кейса оптимизации отдела продаж; требует калибровки под голосового бота.
      </footer>
    </div>
  );
}

function Block({ n, title, icon, children }: { n: string; title: string; icon: React.ReactNode; children: React.ReactNode }) {
  return (
    <section className="report-block mb-5">
      <h2 className="mb-2 flex items-center gap-2 text-base font-medium" style={{ fontFamily: "var(--font-display)" }}>
        <span className="stat-num text-sm text-[var(--color-accent)]">{n}</span>
        <span className="text-[var(--color-accent)]">{icon}</span>{title}
      </h2>
      {children}
    </section>
  );
}

function KPI({ label, value, sub, band }: { label: string; value: string; sub?: string; band?: string }) {
  const cls = band === "bad" ? "band-bad" : band === "good" ? "band-good" : "text-[var(--color-ink)]";
  return (
    <div className="rounded-[var(--radius-md)] border border-[var(--color-border)] bg-[var(--color-bg-card)] p-2.5">
      <div className="text-[10px] uppercase tracking-wide text-[var(--color-ink-muted)]">{label}</div>
      <div className={`stat-num text-xl ${cls}`}>{value}</div>
      {sub && <div className="text-[10px] text-[var(--color-ink-tertiary)]">{sub}</div>}
    </div>
  );
}

function PatternCol({ title, rows, good }: { title: string; rows: { psy_id: string; name: string; share: number; lift_on_advance: number }[]; good?: boolean }) {
  return (
    <div>
      <div className="flex items-center gap-1.5 text-xs font-medium mb-1.5">
        {good ? <ThumbsUp size={13} className="text-[var(--color-band-good)]" /> : <ThumbsDown size={13} className="text-[var(--color-band-bad)]" />}
        {title}
      </div>
      <div className="space-y-1">
        {rows.length === 0 && <p className="text-xs text-[var(--color-ink-tertiary)]">Не обнаружено.</p>}
        {rows.map((p) => (
          <div key={p.psy_id} className="flex items-center justify-between gap-2 text-xs">
            <span className="truncate text-[var(--color-ink-secondary)]">{p.name}</span>
            <span className="shrink-0 stat-num text-[var(--color-ink-tertiary)]">
              {pct(p.share, 2)} · <span className={p.lift_on_advance >= 0 ? "band-good" : "band-bad"}>{p.lift_on_advance >= 0 ? "+" : ""}{(p.lift_on_advance * 100).toFixed(0)}pp</span>
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
