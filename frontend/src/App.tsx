// HashRouter (not BrowserRouter): the app deploys to a GitHub Pages PROJECT subpath
// (/Botamin-BI/). Hash routing makes deep links + refresh work with zero server config
// and no 404.html shim — robust for a static dashboard.
import { HashRouter, Routes, Route, NavLink } from "react-router-dom";
import {
  LayoutDashboard, Filter, AudioLines, Activity, Phone, ListChecks, BookOpen, Lightbulb, SlidersHorizontal, FileText,
} from "lucide-react";
import { lazy, Suspense } from "react";
import Skeleton from "./components/Skeleton";
import AnalysisBanner from "./components/AnalysisBanner";
import { useDashboard } from "./hooks";
import type { Dashboard } from "./types";

const Overview = lazy(() => import("./pages/Overview"));
const FunnelPage = lazy(() => import("./pages/Funnel"));
const VoiceAgent = lazy(() => import("./pages/VoiceAgent"));
const Technical = lazy(() => import("./pages/Technical"));
const CallsPage = lazy(() => import("./pages/Calls"));
const CustDevPage = lazy(() => import("./pages/CustDev"));
const BacklogPage = lazy(() => import("./pages/Backlog"));
const Methodology = lazy(() => import("./pages/Methodology"));
const ReportPage = lazy(() => import("./pages/Report"));
const SettingsPage = lazy(() => import("./pages/Settings"));

const NAV = [
  { to: "/", icon: LayoutDashboard, label: "Продукт", hint: "Общая картина" },
  { to: "/funnel", icon: Filter, label: "Воронка", hint: "S0 → S4, где теряем" },
  { to: "/voice", icon: AudioLines, label: "Голос. агент", hint: "Качество ведения диалога" },
  { to: "/technical", icon: Activity, label: "Техника", hint: "Связь, ASR, инструментовка" },
  { to: "/calls", icon: Phone, label: "Звонки", hint: "Просмотр диалогов" },
  { to: "/custdev", icon: Lightbulb, label: "CustDev", hint: "Голос клиента, Tier 3 инсайты" },
  { to: "/backlog", icon: ListChecks, label: "Бэклог", hint: "Гипотезы и A/B" },
  { to: "/report", icon: FileText, label: "Отчёт клиенту", hint: "Сводка · выгрузка в PDF" },
  { to: "/method", icon: BookOpen, label: "Методика", hint: "Почему так" },
  { to: "/settings", icon: SlidersHorizontal, label: "Настройки", hint: "Конфигурация системы" },
];

function Sidebar({ meta }: { meta: Dashboard | null }) {
  const period =
    meta?.meta.period_from && meta?.meta.period_to
      ? `${meta.meta.period_from} — ${meta.meta.period_to}`
      : null;
  return (
    <nav className="no-print sticky top-0 h-screen w-60 shrink-0 border-r border-[var(--color-border)] bg-[var(--color-bg-card)] px-3 py-6 flex flex-col gap-1 overflow-y-auto">
      <div className="px-3 mb-5">
        <h1 className="text-lg font-medium" style={{ fontFamily: "var(--font-display)" }}>
          Botamin <span className="text-[var(--color-accent)]">BI</span>
        </h1>
        <p className="text-xs text-[var(--color-ink-tertiary)] mt-0.5">Аналитика голосового агента</p>
        {meta && (
          <div className="mt-3 rounded-[var(--radius-md)] bg-[var(--color-bg-card-hover)] px-3 py-2 text-[11px] text-[var(--color-ink-tertiary)] tabular-nums">
            {meta.meta.total_rows.toLocaleString("ru-RU")} звонков
            {period && <><br />{period}</>}
          </div>
        )}
      </div>

      {NAV.map((item) => (
        <NavLink
          key={item.to}
          to={item.to}
          end={item.to === "/"}
          className={({ isActive }) =>
            `group flex flex-col px-3 py-2 rounded-[var(--radius-md)] transition-all duration-[var(--duration-fast)] ${
              isActive
                ? "bg-[var(--color-accent-subtle)] text-[var(--color-accent)]"
                : "text-[var(--color-ink-secondary)] hover:bg-[var(--color-bg-card-hover)] hover:text-[var(--color-ink)]"
            }`
          }
        >
          <span className="flex items-center gap-2.5 text-sm font-medium">
            <item.icon size={17} strokeWidth={1.8} />
            {item.label}
          </span>
          <span className="ml-[27px] text-[10px] text-[var(--color-ink-muted)] leading-tight">{item.hint}</span>
        </NavLink>
      ))}

      <div className="mt-auto px-3 pt-4 border-t border-[var(--color-border)]">
        <p className="text-[10px] text-[var(--color-ink-muted)] leading-relaxed">
          Python 3.13 · React 19 · LLM: Z.ai → Anthropic
        </p>
      </div>
    </nav>
  );
}

export default function App() {
  const { data } = useDashboard();
  return (
    <HashRouter>
      <div className="flex min-h-screen">
        <Sidebar meta={data} />
        <main className="flex-1 overflow-y-auto">
          {data && (
            <div className="no-print px-8 pt-6">
              <AnalysisBanner llm={data.meta.llm} totalRows={data.meta.total_rows} />
            </div>
          )}
          <Suspense
            fallback={
              <div className="p-8 space-y-6">
                <Skeleton h={32} w={300} />
                <div className="grid grid-cols-3 gap-4">
                  <Skeleton h={120} /><Skeleton h={120} /><Skeleton h={120} />
                </div>
              </div>
            }
          >
            <Routes>
              <Route path="/" element={<Overview />} />
              <Route path="/funnel" element={<FunnelPage />} />
              <Route path="/voice" element={<VoiceAgent />} />
              <Route path="/technical" element={<Technical />} />
              <Route path="/calls" element={<CallsPage />} />
              <Route path="/custdev" element={<CustDevPage />} />
              <Route path="/backlog" element={<BacklogPage />} />
              <Route path="/report" element={<ReportPage />} />
              <Route path="/method" element={<Methodology />} />
              <Route path="/settings" element={<SettingsPage />} />
            </Routes>
          </Suspense>
        </main>
      </div>
    </HashRouter>
  );
}
