import { useState, useMemo } from "react";
import { useCallIndex, useCallDetail, fmtDuration, stageColor } from "../hooks";
import Badge from "../components/Badge";
import Skeleton from "../components/Skeleton";
import { Search, X, Volume2, User, Bot, ChevronLeft, ChevronRight, Sparkles, ShieldHalf,
         ThumbsUp, ThumbsDown, Lightbulb, Quote, Wrench, Target, Award } from "lucide-react";
import { stageLabels, pct } from "../format";
import type { QualityScore } from "../types";

const PAGE_SIZE = 50;  // Match pipeline batch size for consistency
const STAGE_FILTERS = [
  { v: "all", l: "Все" }, { v: "-1", l: "Нет контакта" }, { v: "0", l: "Контакт" },
  { v: "1", l: "Согласие" }, { v: "2", l: "Оффер" }, { v: "3", l: "Встреча" }, { v: "4", l: "Квалиф." },
];

export default function CallsPage() {
  const { data: calls, loading } = useCallIndex();
  const [search, setSearch] = useState("");
  const [stageFilter, setStageFilter] = useState("all");
  const [lossFilter, setLossFilter] = useState("all");
  const [page, setPage] = useState(0);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const filtered = useMemo(() => {
    let r = calls;
    if (stageFilter !== "all") r = r.filter((c) => String(c.furthest_stage) === stageFilter);
    if (lossFilter !== "all") r = r.filter((c) => c.loss_layer === lossFilter);
    if (search.trim()) {
      const q = search.toLowerCase();
      r = r.filter((c) => c.id.includes(q) || c.snippet.toLowerCase().includes(q));
    }
    return r;
  }, [calls, stageFilter, lossFilter, search]);

  const paged = filtered.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);
  const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));

  if (loading) return <div className="p-8"><Skeleton h={600} /></div>;

  return (
    <div className="p-8 pt-5 space-y-4 max-w-[1400px]">
      <header>
        <h1 className="text-2xl" style={{ fontFamily: "var(--font-display)" }}>Звонки</h1>
        <p className="mt-1 text-sm text-[var(--color-ink-tertiary)]">
          {calls.length.toLocaleString("ru-RU")} звонков · клик → карточка с транскриптом, разметкой стадий и аудио
        </p>
      </header>

      <div className="flex flex-wrap items-center gap-3">
        <div className="relative flex-1 min-w-[220px] max-w-sm">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-[var(--color-ink-muted)]" />
          <input
            placeholder="Поиск по ID / содержимому…"
            value={search}
            onChange={(e) => { setSearch(e.target.value); setPage(0); }}
            className="w-full pl-9 pr-3 py-2 rounded-[var(--radius-md)] border border-[var(--color-border)] bg-[var(--color-bg-card)] text-sm focus:outline-none focus:border-[var(--color-accent)]"
          />
        </div>
        <Chips value={stageFilter} onChange={(v) => { setStageFilter(v); setPage(0); }} options={STAGE_FILTERS} />
        <Chips value={lossFilter} onChange={(v) => { setLossFilter(v); setPage(0); }}
               options={[{ v: "all", l: "Все потери" }, { v: "context", l: "Контекст" }, { v: "controllable", l: "Промпт" }]} />
      </div>

      <div className="rounded-[var(--radius-xl)] border border-[var(--color-border)] bg-[var(--color-bg-card)] overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-[var(--color-border)] bg-[var(--color-bg-card-hover)] text-[10px] uppercase tracking-wider text-[var(--color-ink-tertiary)]">
              {["ID", "Время", "Длит.", "Стадия", "Исход", "Потеря", "ASR", "Фрагмент"].map((h) => (
                <th key={h} className="text-left py-2.5 px-4 font-medium">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {paged.map((c) => (
              <tr key={c.id} onClick={() => setSelectedId(c.id)}
                  className="border-b border-[var(--color-border)]/50 hover:bg-[var(--color-accent-bg)] cursor-pointer">
                <td className="py-2 px-4 stat-num text-xs text-[var(--color-accent)]">{c.id}</td>
                <td className="py-2 px-4 text-xs text-[var(--color-ink-tertiary)]">{c.datetime.slice(5, 16)}</td>
                <td className="py-2 px-4 stat-num text-xs">{fmtDuration(c.duration_sec)}</td>
                <td className="py-2 px-4">
                  <span className="inline-flex items-center gap-1.5 text-xs">
                    <span className="w-2 h-2 rounded-full" style={{ background: stageColor(c.furthest_stage) }} />
                    {stageLabels[c.furthest_stage] ?? c.furthest_stage}
                  </span>
                </td>
                <td className="py-2 px-4 text-xs text-[var(--color-ink-secondary)]">{c.outcome}</td>
                <td className="py-2 px-4 text-xs">
                  {c.loss_layer === "context" ? <span className="band-ok">контекст</span>
                    : c.loss_layer === "controllable" ? <span className="band-bad">промпт</span>
                    : <span className="text-[var(--color-ink-muted)]">—</span>}
                </td>
                <td className="py-2 px-4 text-xs text-[var(--color-ink-tertiary)]">{c.asr_severity !== "none" ? c.asr_severity : ""}</td>
                <td className="py-2 px-4 text-xs text-[var(--color-ink-tertiary)] max-w-[260px] truncate">{c.snippet}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="flex items-center justify-between">
        <p className="text-xs text-[var(--color-ink-tertiary)]">Показано {paged.length} из {filtered.length.toLocaleString("ru-RU")}</p>
        <div className="flex items-center gap-2">
          <button onClick={() => setPage(Math.max(0, page - 1))} disabled={page === 0}
                  className="p-1.5 rounded-[var(--radius-sm)] border border-[var(--color-border)] disabled:opacity-30 hover:bg-[var(--color-bg-card-hover)]"><ChevronLeft size={14} /></button>
          <span className="text-xs stat-num">{page + 1} / {totalPages}</span>
          <button onClick={() => setPage(Math.min(totalPages - 1, page + 1))} disabled={page >= totalPages - 1}
                  className="p-1.5 rounded-[var(--radius-sm)] border border-[var(--color-border)] disabled:opacity-30 hover:bg-[var(--color-bg-card-hover)]"><ChevronRight size={14} /></button>
        </div>
      </div>

      {selectedId && <CallDrawer id={selectedId} pageHint={calls.find(c => c.id === selectedId)?.page} onClose={() => setSelectedId(null)} />}
    </div>
  );
}

function Chips({ value, onChange, options }: { value: string; onChange: (v: string) => void; options: { v: string; l: string }[] }) {
  return (
    <div className="flex items-center gap-1.5 flex-wrap">
      {options.map((o) => (
        <button key={o.v} onClick={() => onChange(o.v)}
          className={`px-2.5 py-1 rounded-full text-xs font-medium transition-colors ${
            value === o.v ? "bg-[var(--color-accent)] text-white" : "bg-[var(--color-bg-card-hover)] text-[var(--color-ink-secondary)] hover:bg-[var(--color-border)]"
          }`}>{o.l}</button>
      ))}
    </div>
  );
}

const STAGE_KEYS = [
  { k: "consent", l: "Согласие" }, { k: "offer_engaged", l: "Оффер" },
  { k: "meeting_agreed", l: "Встреча" }, { k: "qualified", l: "Квалификация" },
];

function CallDrawer({ id, pageHint, onClose }: { id: string; pageHint?: string; onClose: () => void }) {
  const { data, loading } = useCallDetail(id, pageHint);
  return (
    <>
      <div className="fixed inset-0 bg-black/10 z-40" onClick={onClose} />
      <div className="fixed top-0 right-0 h-full w-[680px] max-w-full bg-[var(--color-bg-card)] border-l border-[var(--color-border)] shadow-[var(--shadow-drawer)] z-50 overflow-y-auto"
           style={{ animation: "slide-in-right .3s var(--ease-out-expo)" }}>
        <style>{`@keyframes slide-in-right{from{transform:translateX(100%)}to{transform:translateX(0)}}`}</style>
        <div className="sticky top-0 bg-[var(--color-bg-card)] border-b border-[var(--color-border)] px-5 py-4 flex items-center justify-between z-10">
          <div>
            <h3 className="text-sm font-medium" style={{ fontFamily: "var(--font-display)" }}>Звонок {id}</h3>
            {data && <p className="text-xs text-[var(--color-ink-tertiary)] mt-0.5">{data.datetime.slice(0, 16)} · {fmtDuration(data.duration_sec)} · {stageLabels[data.furthest_stage] ?? data.furthest_stage}</p>}
          </div>
          <button onClick={onClose} className="p-1.5 rounded-[var(--radius-sm)] hover:bg-[var(--color-bg-card-hover)]"><X size={18} /></button>
        </div>

        {loading ? (
          <div className="p-5 space-y-3"><Skeleton h={20} /><Skeleton h={60} /><Skeleton h={200} /></div>
        ) : data ? (
          <div className="p-5 space-y-5">
            <div className="flex items-center gap-2 text-xs">
              {data.source === "llm"
                ? <span className="inline-flex items-center gap-1 bandbg-good rounded-full px-2 py-0.5"><Sparkles size={11} />LLM</span>
                : <span className="inline-flex items-center gap-1 bandbg-ok rounded-full px-2 py-0.5"><ShieldHalf size={11} />эвристика</span>}
              {data.disqualified && <Badge variant="negative">дисквалификация</Badge>}
              <span className="text-[var(--color-ink-tertiary)]">{data.summary}</span>
            </div>

            {/* V4 quality + gap */}
            {data.quality && <QualityGap q={data.quality} />}

            {/* Stage evidence */}
            <div>
              <h4 className="text-[10px] font-medium uppercase tracking-wider text-[var(--color-ink-tertiary)] mb-2">Разметка стадий (по словам клиента)</h4>
              <div className="grid grid-cols-2 gap-2">
                {STAGE_KEYS.map((s) => {
                  const ev = data.stage_evidence?.[s.k];
                  const reached = ev?.reached;
                  return (
                    <div key={s.k} className={`rounded-[var(--radius-md)] border px-3 py-2 ${reached ? "border-[var(--color-band-good)]/40 bandbg-good" : "border-[var(--color-border)] bg-[var(--color-bg-card-hover)]"}`}>
                      <div className="flex items-center justify-between">
                        <span className="text-xs font-medium">{s.l}</span>
                        <span className="text-xs">{reached ? "✓" : "—"}</span>
                      </div>
                      {reached && ev?.quote && <p className="mt-0.5 text-[10px] italic text-[var(--color-ink-tertiary)]">«{ev.quote.slice(0, 80)}»</p>}
                    </div>
                  );
                })}
              </div>
            </div>

            {/* Voice metrics */}
            <div className="grid grid-cols-3 gap-3">
              <Tile label="Отзывчивость" v={data.voice.responsiveness.toFixed(2)} />
              <Tile label="Реплик-перепрос." v={String(data.voice.repair_attempts)} />
              <Tile label="Речь бота" v={pct(data.voice.bot_talk_share, 0)} />
            </div>

            {/* Psychological patterns (with names + evidence) */}
            {data.detected_patterns?.length > 0 && (
              <div>
                <h4 className="text-[10px] font-medium uppercase tracking-wider text-[var(--color-ink-tertiary)] mb-2">Психологические паттерны бота</h4>
                <div className="space-y-1.5">
                  {data.detected_patterns.map((p, i) => {
                    const bad = p.polarity === "negative";
                    return (
                      <div key={i} className="flex items-start gap-2 text-xs">
                        {bad ? <ThumbsDown size={13} className="mt-0.5 shrink-0 text-[var(--color-band-bad)]" />
                             : <ThumbsUp size={13} className="mt-0.5 shrink-0 text-[var(--color-band-good)]" />}
                        <Badge variant={bad ? "negative" : "positive"}>{p.id}</Badge>
                        <div className="min-w-0">
                          <span className="text-[var(--color-ink-secondary)]">{p.name || p.id}</span>
                          {p.quote && <p className="text-[10px] italic text-[var(--color-ink-muted)] mt-0.5">«{p.quote.slice(0, 90)}»</p>}
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}

            {/* Objections (with root cause) */}
            {data.objections?.length > 0 && (
              <div>
                <h4 className="text-[10px] font-medium uppercase tracking-wider text-[var(--color-ink-tertiary)] mb-2">Возражения</h4>
                <div className="space-y-1.5">
                  {data.objections.map((o, i) => (
                    <div key={i} className="text-xs">
                      <Badge variant="warning">{o.type}</Badge>
                      {o.quote && <span className="ml-1.5 italic text-[var(--color-ink-tertiary)]">«{o.quote.slice(0, 80)}»</span>}
                      {o.root_cause && <p className="text-[10px] text-[var(--color-ink-muted)] mt-0.5">причина: {o.root_cause}</p>}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Product-intel / CustDev (LLM) */}
            {(data.product_intel?.insights?.length || hasJTBD(data.product_intel)) && (
              <div>
                <h4 className="text-[10px] font-medium uppercase tracking-wider text-[var(--color-ink-tertiary)] mb-2">
                  <Lightbulb size={12} className="inline mr-1 text-[var(--color-secondary)]" />Продуктовые инсайты (CustDev)
                </h4>
                {hasJTBD(data.product_intel) && (
                  <div className="rounded-[var(--radius-md)] bg-[var(--color-bg-card-hover)] px-3 py-2 mb-2 text-xs space-y-0.5">
                    {data.product_intel!.jtbd.functional && <p><b className="text-[var(--color-ink)]">JTBD:</b> {data.product_intel!.jtbd.functional}</p>}
                    {data.product_intel!.jtbd.trigger && <p className="text-[var(--color-ink-tertiary)]">Триггер: {data.product_intel!.jtbd.trigger}</p>}
                  </div>
                )}
                <div className="space-y-1.5">
                  {data.product_intel?.insights?.map((it, i) => (
                    <div key={i} className="flex items-start gap-1.5 text-xs border-l-2 border-[var(--color-accent-subtle)] pl-2 py-0.5">
                      <Quote size={11} className="mt-0.5 shrink-0 text-[var(--color-ink-muted)]" />
                      <div className="min-w-0">
                        <Badge>{it.category}</Badge>{" "}
                        <span className="text-[var(--color-ink-secondary)]">{it.insight}</span>
                        {it.quote && <p className="italic text-[var(--color-ink-muted)] mt-0.5">«{it.quote.slice(0, 100)}»</p>}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Recommendations */}
            {data.recommendations && data.recommendations.length > 0 && (
              <div>
                <h4 className="text-[10px] font-medium uppercase tracking-wider text-[var(--color-ink-tertiary)] mb-2">
                  <Wrench size={12} className="inline mr-1 text-[var(--color-accent)]" />Что подкрутить
                </h4>
                <ul className="space-y-1">
                  {data.recommendations.map((r, i) => (
                    <li key={i} className="text-xs text-[var(--color-ink-secondary)] flex gap-1.5">
                      <span className="text-[var(--color-accent)]">•</span><span>{r}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {data.audio_url && (
              <div>
                <h4 className="text-[10px] font-medium uppercase tracking-wider text-[var(--color-ink-tertiary)] mb-2"><Volume2 size={12} className="inline mr-1" />Аудио</h4>
                <audio controls className="w-full" preload="none"><source src={data.audio_url} type="audio/wav" /></audio>
              </div>
            )}

            <div>
              <h4 className="text-[10px] font-medium uppercase tracking-wider text-[var(--color-ink-tertiary)] mb-3">Транскрипт</h4>
              <div className="space-y-2">
                {data.transcript.map((t, i) => {
                  const isBot = t.role === "bot";
                  return (
                    <div key={i} className={`flex gap-2.5 ${isBot ? "" : "flex-row-reverse"}`}>
                      <div className={`w-7 h-7 rounded-full flex items-center justify-center shrink-0 text-white ${isBot ? "bg-[var(--color-accent)]" : "bg-[var(--color-secondary)]"}`}>
                        {isBot ? <Bot size={14} /> : <User size={14} />}
                      </div>
                      <div className={`max-w-[85%] rounded-[var(--radius-lg)] px-3.5 py-2.5 text-sm leading-relaxed ${isBot ? "bg-[var(--color-accent-bg)]" : "bg-[var(--color-bg-card-hover)]"} text-[var(--color-ink)]`}>
                        {t.text}
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          </div>
        ) : (
          <div className="p-5 text-sm text-[var(--color-ink-tertiary)]">Не удалось загрузить данные.</div>
        )}
      </div>
    </>
  );
}

function Tile({ label, v }: { label: string; v: string }) {
  return (
    <div className="rounded-[var(--radius-md)] bg-[var(--color-bg-card-hover)] p-3 text-center">
      <div className="text-[10px] uppercase tracking-wider text-[var(--color-ink-tertiary)]">{label}</div>
      <div className="stat-num text-lg mt-0.5">{v}</div>
    </div>
  );
}

function hasJTBD(pi?: { jtbd?: { functional?: string; emotional?: string; trigger?: string } }) {
  const j = pi?.jtbd;
  return !!(j && (j.functional || j.emotional || j.trigger));
}

const GRADE_CLR: Record<string, string> = {
  A: "var(--color-band-good)", B: "var(--color-band-good)", C: "var(--color-band-ok)",
  D: "var(--color-band-bad)", F: "var(--color-band-bad)",
};

function QualityGap({ q }: { q: QualityScore }) {
  const gapBand = q.gap.gap > 1.5 ? "band-bad" : q.gap.gap < -1.5 ? "" : "band-good";
  const sign = q.gap.gap >= 0 ? "+" : "";
  return (
    <div className="rounded-[var(--radius-md)] border border-[var(--color-border)] bg-[var(--color-bg-card-hover)] p-3.5">
      <div className="flex items-center justify-between mb-3">
        <h4 className="text-[10px] font-medium uppercase tracking-wider text-[var(--color-ink-tertiary)]">
          <Award size={12} className="inline mr-1" />Качество ведения (V4)
        </h4>
        <span className="stat-num text-2xl" style={{ color: GRADE_CLR[q.grade] || "var(--color-ink)" }} title={q.grade_name}>
          {q.grade}
        </span>
      </div>
      <div className="grid grid-cols-3 gap-2 mb-3">
        <MiniLayer label="Macro" v={q.macro} />
        <MiniLayer label="Micro" v={q.micro} />
        <MiniLayer label="Overlap" v={q.overlap} />
      </div>
      <div className="flex items-center justify-between text-xs border-t border-[var(--color-border)] pt-2.5">
        <span className="text-[var(--color-ink-tertiary)]">Качество <b className="stat-num text-[var(--color-ink)]">{q.total.toFixed(1)}</b> · Результат <b className="stat-num text-[var(--color-ink)]">{q.outcome.toFixed(1)}</b></span>
        <span className="flex items-center gap-1"><Target size={12} className="text-[var(--color-ink-muted)]" />
          <span className={`stat-num ${gapBand}`}>gap {sign}{q.gap.gap.toFixed(1)}</span></span>
      </div>
      <p className="mt-1.5 text-[11px] text-[var(--color-ink-tertiary)] leading-snug">{q.gap.interpretation}</p>
    </div>
  );
}

function MiniLayer({ label, v }: { label: string; v: number }) {
  return (
    <div>
      <div className="flex items-center justify-between text-[10px] text-[var(--color-ink-tertiary)] mb-0.5">
        <span>{label}</span><span className="stat-num">{v.toFixed(1)}</span>
      </div>
      <div className="h-1.5 rounded-full bg-[var(--color-border)] overflow-hidden">
        <div className="h-full rounded-full bg-[var(--color-accent)]" style={{ width: `${Math.max(0, Math.min(100, v * 10))}%` }} />
      </div>
    </div>
  );
}
