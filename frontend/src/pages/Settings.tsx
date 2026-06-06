import { useState, useMemo } from "react";
import { useDashboard } from "../hooks";
import {
  useOverrides, setOverrides, resetOverrides, autoFromValue, bandOf,
  type Overrides,
} from "../thresholds";
import Card from "../components/Card";
import Skeleton from "../components/Skeleton";
import DataSourceModal from "../components/DataSourceModal";
import ScopeSelector from "../components/ScopeSelector";
import { fmtValue, bandText } from "../format";
import type { Dashboard, Metric, ThresholdDef, Fmt } from "../types";
import { Wand2, RefreshCw, RotateCcw, Check, Database, Brain, Upload, FileSpreadsheet, Globe, Plus } from "lucide-react";

/** Collect current value + fmt + name for every metric that has a thr_key. */
function currentValues(d: Dashboard): Record<string, { value: number; name: string; fmt: Fmt }> {
  const out: Record<string, { value: number; name: string; fmt: Fmt }> = {};
  const push = (m: Metric) => {
    if (m.thr_key) out[m.thr_key] = { value: m.value, name: m.name, fmt: m.fmt };
  };
  d.reach.metrics.forEach(push);
  d.drivers.forEach((x) => push(x as Metric));
  push(d.nsm as Metric);
  d.quality.metrics.forEach(push);
  d.guardrails.forEach(push);
  return out;
}

// pct thresholds are stored 0..1 but shown to humans as percent.
// Thresholds use TENTHS (1 decimal) — a deliberately coarser precision than the
// hundredths used for live metrics elsewhere (you tune a band, not report a number).
const toDisplay = (v: number, fmt: Fmt) => (fmt === "pct" ? Math.round(v * 1000) / 10 : v);
const fromDisplay = (s: string, fmt: Fmt) => {
  const n = parseFloat(s.replace(",", "."));
  if (Number.isNaN(n)) return 0;
  return fmt === "pct" ? n / 100 : n;
};
const unit = (fmt: Fmt) => (fmt === "pct" ? "%" : fmt === "sec" ? "сек" : "");

export default function Settings() {
  const { data, loading } = useDashboard();
  const overrides = useOverrides();
  const [draft, setDraft] = useState<Overrides>(() => ({ ...overrides }));
  const [showDataModal, setShowDataModal] = useState(false);
  // Chosen analysis scope. Data is precomputed, so this is the scope to APPLY on the
  // next pipeline run; we persist the choice and show the exact command.
  const [scopePref, setScopePref] = useState<string>(() => {
    try { return localStorage.getItem("botamin.scope_pref") || ""; } catch { return ""; }
  });
  const dataScope = data?.meta.llm?.scope || "focus";
  const chosenScope = scopePref || dataScope;
  const changeScope = (v: string) => {
    setScopePref(v);
    try { localStorage.setItem("botamin.scope_pref", v); } catch { /* ignore */ }
  };

  // "Пересчитать звонки" — trigger the real LLM re-analysis. A static site can't run
  // Python, so we dispatch the GitHub Actions workflow (deploy.yml) which re-runs the
  // pipeline with the chosen scope and redeploys. Needs a fine-grained GitHub token
  // (Actions: write) — stored only in this browser, sent only to api.github.com.
  const GH = { owner: "Gorby200", repo: "Botamin-BI", workflow: "deploy.yml", ref: "main" };
  const [ghToken, setGhTokenState] = useState<string>(() => {
    try { return localStorage.getItem("botamin.gh_token") || ""; } catch { return ""; }
  });
  const setGhToken = (v: string) => {
    setGhTokenState(v);
    try { localStorage.setItem("botamin.gh_token", v); } catch { /* ignore */ }
  };
  const [recalc, setRecalc] = useState<{ state: "idle" | "sending" | "done" | "error"; msg: string }>({ state: "idle", msg: "" });
  const recalcCalls = async () => {
    if (!ghToken.trim()) { setRecalc({ state: "error", msg: "Вставьте GitHub-токен ниже." }); return; }
    setRecalc({ state: "sending", msg: "" });
    try {
      const res = await fetch(
        `https://api.github.com/repos/${GH.owner}/${GH.repo}/actions/workflows/${GH.workflow}/dispatches`,
        {
          method: "POST",
          headers: {
            Accept: "application/vnd.github+json",
            Authorization: `Bearer ${ghToken.trim()}`,
            "X-GitHub-Api-Version": "2022-11-28",
          },
          body: JSON.stringify({ ref: GH.ref, inputs: { llm_scope: chosenScope } }),
        }
      );
      if (res.status === 204) {
        setRecalc({ state: "done", msg: `Запущено в режиме «${chosenScope}». Сборка идёт на GitHub Actions (~5–10 мин), затем обновите страницу.` });
      } else {
        let detail = "";
        try { detail = (await res.json())?.message || ""; } catch { /* ignore */ }
        setRecalc({ state: "error", msg: `Ошибка ${res.status}. ${detail}` });
      }
    } catch (e: any) {
      setRecalc({ state: "error", msg: `Не удалось отправить запрос: ${e?.message || e}` });
    }
  };

  const defs = data?.thresholds_defaults ?? [];
  const current = useMemo(() => (data ? currentValues(data) : {}), [data]);
  const groups = useMemo(() => {
    const g: Record<string, ThresholdDef[]> = {};
    defs.forEach((d) => (g[d.group] ||= []).push(d));
    return g;
  }, [defs]);

  if (loading || !data)
    return <div className="p-8 space-y-4"><Skeleton h={40} w={320} /><Skeleton h={300} /></div>;

  const effGood = (d: ThresholdDef) => draft[d.key]?.good ?? d.good;
  const effOk = (d: ThresholdDef) => draft[d.key]?.ok ?? d.ok;

  const setField = (key: string, field: "good" | "ok", value: number, def: ThresholdDef) => {
    setDraft((prev) => {
      const base = prev[key] ?? { good: def.good, ok: def.ok };
      return { ...prev, [key]: { ...base, [field]: value } };
    });
  };

  const autoDerive = () => {
    const next: Overrides = {};
    defs.forEach((d) => {
      const cur = current[d.key];
      if (cur) next[d.key] = autoFromValue(cur.value, d.direction, d.fmt);
    });
    setDraft(next);
  };

  const apply = () => setOverrides(draft);
  const reset = () => { resetOverrides(); setDraft({}); };

  const dirty = JSON.stringify(draft) !== JSON.stringify(overrides);

  return (
    <div className="p-8 pt-5 space-y-6 max-w-[1100px]">
      <header className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl" style={{ fontFamily: "var(--font-display)" }}>Настройки · конфигурация</h1>
          <p className="mt-1 text-sm text-[var(--color-ink-tertiary)]">
            Источник данных, LLM-анализ и пороги метрик — всё настраивается здесь.
            Цвета и вердикты пересчитываются мгновенно.
          </p>
        </div>
      </header>

      {/* Actions */}
      <div className="flex flex-wrap items-center gap-3">
        <button onClick={autoDerive}
          className="inline-flex items-center gap-2 rounded-[var(--radius-md)] border border-[var(--color-accent)] bg-[var(--color-accent-subtle)] px-4 py-2 text-sm font-medium text-[var(--color-accent)] hover:opacity-90 transition">
          <Wand2 size={15} /> Определить автоматически по датасету
        </button>
        <button onClick={apply} disabled={!dirty}
          className={`inline-flex items-center gap-2 rounded-[var(--radius-md)] px-4 py-2 text-sm font-medium transition ${
            dirty ? "bg-[var(--color-accent)] text-white hover:opacity-90" : "bg-[var(--color-bg-card-hover)] text-[var(--color-ink-muted)] cursor-default"}`}>
          <RefreshCw size={15} /> Пересчитать и применить
        </button>
        <button onClick={reset}
          className="inline-flex items-center gap-2 rounded-[var(--radius-md)] border border-[var(--color-border)] px-4 py-2 text-sm text-[var(--color-ink-secondary)] hover:bg-[var(--color-bg-card-hover)] transition">
          <RotateCcw size={15} /> Сбросить к дефолтам
        </button>
        {dirty && <span className="text-xs text-[var(--color-band-ok)]">● есть несохранённые изменения</span>}
        {!dirty && Object.keys(overrides).length > 0 && (
          <span className="inline-flex items-center gap-1 text-xs text-[var(--color-band-good)]"><Check size={13} /> применены пользовательские пороги</span>
        )}
      </div>

      <p className="text-xs text-[var(--color-ink-muted)]">
        «Определить автоматически» ставит <b>приемлемо = текущий уровень</b> по датасету, а <b>хорошо = реалистичный стретч</b> (±25%).
        Дальше можно поправить вручную. Значения хранятся локально в браузере.
      </p>

      {/* Data Source Section */}
      <Card
        title="Источник данных"
        subtitle="Откуда берутся звонки для анализа"
        icon={<Database size={16} className="text-[var(--color-accent)]" />}
      >
        <div className="space-y-3">
          <div className="rounded-md bg-[var(--color-bg-card-hover)] p-3">
            <div className="flex items-center gap-2 text-sm">
              {data?.meta.source?.includes("sheets") || data?.meta.source?.includes("docs.google") ? (
                <Globe size={14} className="text-[var(--color-secondary)]" />
              ) : (
                <FileSpreadsheet size={14} className="text-[var(--color-secondary)]" />
              )}
              <span className="font-medium">
                {data?.meta.source?.includes("sheets") || data?.meta.source?.includes("docs.google")
                  ? "Google Sheets"
                  : "Локальный файл"}
              </span>
            </div>
            <p className="text-xs text-[var(--color-ink-muted)] mt-1">
              {data?.meta.period_from && data?.meta.period_to
                ? `${data.meta.period_from} — ${data.meta.period_to}`
                : "Период не указан"}
              {" · "}{data?.meta.total_rows?.toLocaleString("ru-RU")} звонков
            </p>
          </div>

          <button
            onClick={() => setShowDataModal(true)}
            className="w-full rounded-md border border-dashed border-[var(--color-border)] p-4 text-center hover:border-[var(--color-accent)] hover:bg-[var(--color-accent-subtle)] transition-colors group"
          >
            <div className="w-12 h-12 rounded-full bg-[var(--color-bg-card-hover)] flex items-center justify-center mx-auto mb-3 group-hover:bg-[var(--color-accent)] transition-colors">
              <Plus size={24} className="text-[var(--color-ink-muted)] group-hover:text-white transition-colors" />
            </div>
            <p className="text-sm font-medium text-[var(--color-ink)] mb-1">
              Загрузить новый датасет
            </p>
            <p className="text-xs text-[var(--color-ink-muted)]">
              Google Sheets или CSV/XLSX файл → Анализ через 2-3 минуты
            </p>
          </button>
        </div>
      </Card>

      {/* LLM Configuration Section */}
      <Card
        title="LLM конфигурация"
        subtitle="Глубина AI-анализа звонков"
        icon={<Brain size={16} className="text-[var(--color-accent)]" />}
      >
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-sm font-medium text-[var(--color-ink)]">Провайдер</span>
            <span className="text-sm text-[var(--color-ink-secondary)]">
              {data?.meta.llm?.provider === "zhipu" ? "Zhipu GLM" :
               data?.meta.llm?.provider === "anthropic" ? "Anthropic Claude" :
               "Не настроен"}
            </span>
          </div>

          <div className="flex flex-wrap items-center justify-between gap-2">
            <span className="text-sm font-medium text-[var(--color-ink)]">Глубина анализа</span>
            <ScopeSelector active={chosenScope} onChange={changeScope} size="md" />
          </div>

          {chosenScope !== dataScope ? (
            <div className="rounded-md bandbg-ok px-3 py-2 text-xs text-[var(--color-ink-secondary)]">
              Текущие данные собраны в режиме <b>{dataScope}</b>. Вы выбрали <b>{chosenScope}</b> — чтобы применить,
              перезапустите пайплайн с этим охватом:
              <code className="mt-1.5 block rounded bg-[var(--color-bg-card)] px-2 py-1 text-[var(--color-accent)]">
                python -m pipeline --file data/raw.csv --llm-scope {chosenScope}
              </code>
              <span className="mt-1 block text-[var(--color-ink-muted)]">
                или в GitHub Actions: Run workflow → llm_scope = {chosenScope}.
              </span>
            </div>
          ) : (
            <p className="text-xs text-[var(--color-ink-muted)]">
              Данные собраны в этом охвате. Охват влияет на стоимость и время анализа.
            </p>
          )}

          {/* Recalculate calls — dispatch the LLM re-analysis (GitHub Actions) */}
          <div className="border-t border-[var(--color-border)] pt-3 mt-1 space-y-2">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div>
                <div className="text-sm font-medium text-[var(--color-ink)]">Пересчитать звонки</div>
                <div className="text-[11px] text-[var(--color-ink-muted)]">
                  Отправит выборку «{chosenScope}» в LLM на анализ и пересоберёт дашборд (GitHub Actions).
                </div>
              </div>
              <button onClick={recalcCalls} disabled={recalc.state === "sending"}
                className="inline-flex items-center gap-2 rounded-[var(--radius-md)] bg-[var(--color-accent)] px-4 py-2 text-sm font-medium text-white hover:opacity-90 disabled:opacity-50">
                <RefreshCw size={15} className={recalc.state === "sending" ? "animate-spin" : ""} />
                Пересчитать ({chosenScope})
              </button>
            </div>
            <input
              type="password"
              value={ghToken}
              onChange={(e) => setGhToken(e.target.value)}
              placeholder="GitHub fine-grained token (Actions: write)"
              className="w-full rounded-[var(--radius-md)] border border-[var(--color-border)] bg-[var(--color-bg-card-hover)] px-3 py-1.5 text-sm focus:outline-none focus:border-[var(--color-accent)]"
            />
            {recalc.msg && (
              <p className={`text-xs ${recalc.state === "error" ? "band-bad" : "band-good"}`}>
                {recalc.msg}{" "}
                {recalc.state === "done" && (
                  <a className="text-[var(--color-accent)] underline" target="_blank" rel="noreferrer"
                     href={`https://github.com/${GH.owner}/${GH.repo}/actions`}>Открыть Actions →</a>
                )}
              </p>
            )}
            <p className="text-[11px] leading-relaxed text-[var(--color-ink-muted)]">
              Нужен fine-grained токен GitHub с правом <b>Actions: Read and write</b> на репозиторий
              <code className="text-[var(--color-accent)]"> {GH.owner}/{GH.repo}</code>. Хранится только в этом
              браузере, отправляется только на api.github.com. У репозитория должен быть источник данных
              (переменная DEFAULT_SHEET_URL или закоммиченный CSV).
            </p>
          </div>
        </div>
      </Card>

      {/* Threshold groups */}
      {Object.entries(groups).map(([group, items]) => (
        <Card key={group} title={group} subtitle={`${items.length} порог(ов)`}>
          <div className="space-y-1">
            <div className="grid grid-cols-[1fr_auto_auto_auto_auto] gap-3 items-center px-1 pb-2 text-[10px] uppercase tracking-wider text-[var(--color-ink-muted)]">
              <span>Метрика</span><span className="text-right w-20">Сейчас</span>
              <span className="text-right w-32">Хорошо ≥/≤</span><span className="text-right w-32">Приемлемо</span>
              <span className="text-right w-20">Дефолт</span>
            </div>
            {items.map((d) => {
              const cur = current[d.key];
              const band = cur ? bandOf(cur.value, effGood(d), effOk(d), d.direction) : "neutral";
              return (
                <div key={d.key} className="grid grid-cols-[1fr_auto_auto_auto_auto] gap-3 items-center py-2 border-b border-[var(--color-border)] last:border-0">
                  <div className="min-w-0">
                    <div className="text-sm text-[var(--color-ink)]">{d.label}</div>
                    <div className="text-[10px] text-[var(--color-ink-muted)]">
                      {d.direction === "higher" ? "больше — лучше" : "меньше — лучше"} · {d.key}
                    </div>
                  </div>
                  <div className="w-20 text-right">
                    {cur ? <span className={`stat-num text-sm ${bandText[band]}`}>{cur.fmt === "pct" ? `${(cur.value * 100).toFixed(1)}%` : fmtValue(cur.value, cur.fmt)}</span>
                         : <span className="text-xs text-[var(--color-ink-muted)]">—</span>}
                  </div>
                  <NumInput value={effGood(d)} fmt={d.fmt} onChange={(v) => setField(d.key, "good", v, d)} />
                  <NumInput value={effOk(d)} fmt={d.fmt} onChange={(v) => setField(d.key, "ok", v, d)} />
                  <div className="w-20 text-right text-[11px] text-[var(--color-ink-muted)] tabular-nums">
                    {toDisplay(d.good, d.fmt)}{unit(d.fmt)} / {toDisplay(d.ok, d.fmt)}{unit(d.fmt)}
                  </div>
                </div>
              );
            })}
          </div>
        </Card>
      ))}

      {showDataModal && <DataSourceModal onClose={() => setShowDataModal(false)} />}
    </div>
  );
}

function NumInput({ value, fmt, onChange }: { value: number; fmt: Fmt; onChange: (v: number) => void }) {
  const step = fmt === "pct" ? 0.1 : fmt === "sec" ? 10 : 0.05;
  const display = toDisplay(value, fmt);

  // pct is stored 0..1: 0.1 display-step (a tenth of a percent) = 0.001 stored.
  const increment = () => onChange(value + (fmt === "pct" ? 0.001 : step));
  const decrement = () => onChange(value - (fmt === "pct" ? 0.001 : step));

  return (
    <div className="w-28 flex items-center justify-end gap-1.5">
      <button
        onClick={decrement}
        className="p-1 rounded-l-[var(--radius-sm)] border border-r-0 border-[var(--color-border)] bg-[var(--color-bg-card-hover)] text-[var(--color-ink-secondary)] hover:bg-[var(--color-accent-subtle)] hover:text-[var(--color-accent)] transition-colors"
        tabIndex={-1}
      >
        −
      </button>
      <input
        type="number"
        step={step}
        value={display}
        onChange={(e) => onChange(fromDisplay(e.target.value, fmt))}
        className="w-16 rounded-none border-y border-[var(--color-border)] bg-[var(--color-bg-card-hover)] px-2 py-1 text-right text-sm tabular-nums focus:outline-none focus:border-[var(--color-accent)] [&::-webkit-inner-spin-button]:appearance-none [&::-webkit-outer-spin-button]:appearance-none [-moz-appearance:textfield]"
      />
      <button
        onClick={increment}
        className="p-1 rounded-r-[var(--radius-sm)] border border-l-0 border-[var(--color-border)] bg-[var(--color-bg-card-hover)] text-[var(--color-ink-secondary)] hover:bg-[var(--color-accent-subtle)] hover:text-[var(--color-accent)] transition-colors"
        tabIndex={-1}
      >
        +
      </button>
      <span className="w-5 text-[10px] text-[var(--color-ink-muted)]">{unit(fmt)}</span>
    </div>
  );
}
