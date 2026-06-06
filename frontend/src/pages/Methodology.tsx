import { useDashboard } from "../hooks";
import { pct } from "../format";
import { PhoneCall, MessageSquare, ArrowRight } from "lucide-react";
import type { ReactNode } from "react";

export default function Methodology() {
  const { data } = useDashboard();
  const nsm = data?.nsm.value;
  const ctx = data?.loss_attribution.context_share;
  const ctrl = data?.loss_attribution.controllable_share;

  return (
    <div className="p-8 pt-5 max-w-[860px] space-y-7">
      <header>
        <h1 className="text-2xl" style={{ fontFamily: "var(--font-display)" }}>Методика</h1>
        <p className="mt-1 text-sm text-[var(--color-ink-tertiary)]">
          Как устроен инструмент, какие метрики выбраны и почему именно они — от простого к сложному.
        </p>
      </header>

      <Section n="1" title="Зачем этот дашборд">
        <p>
          Цель аналитика на проекте — <b>повышать конверсию</b> голосового бота. Раньше он работал с сырой
          выгрузкой. Дашборд даёт общую картину, показывает, <b>на каком шаге бот теряет клиента</b>, и куда
          направить усилия. Главный принцип всей методики: <b>чинить только то, что промпт реально двигает</b>.
        </p>
      </Section>

      <Section n="2" title="Две вещи, которые нельзя смешивать: Связь и Диалог">
        <p className="mb-4">
          Звонок может провалиться по двум совершенно разным причинам. Если их смешать в одну воронку,
          аналитик будет «улучшать промпт» там, где промпт бессилен.
        </p>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <LayerCard icon={<PhoneCall size={16} />} tone="ok" title="Контекст (связь)"
            body="Дозвон, качество линии, обвал ASR («не слышу», «алло», «что?»), мгновенный сброс. Это зона диалера/телефонии/ASR. Промпт здесь НЕ помогает."
            foot={ctx != null ? `Сейчас: ${pct(ctx, 0)} потерь` : ""} />
          <LayerCard icon={<MessageSquare size={16} />} tone="accent" title="Управляемое (промпт)"
            body="Опенер → оффер → встреча → квалификация. Всё, что бот говорит и как ведёт диалог. Именно это аналитик правит и проверяет A/B-тестами."
            foot={ctrl != null ? `Сейчас: ${pct(ctrl, 0)} потерь` : ""} />
        </div>
      </Section>

      <Section n="3" title="Воронка S0 → S4 (клиент-привязанная)">
        <p className="mb-3">
          Бот ведёт клиента по 4 задачам по порядку. <b>Железное правило:</b> стадия засчитывается только если её
          подтверждают <b>слова самого клиента</b>, а не действия бота. Бот предложил встречу ≠ встреча; клиент
          сказал «да, давайте завтра» = встреча. Это исправляет главную ошибку прежней версии, где встреча
          засчитывалась по фразе бота (отсюда абсурдные 86% конверсии).
        </p>
        <Table rows={[
          ["S0 · Контакт", "Клиент вступил в разговор (сказал хоть реплику по делу)"],
          ["S1 · Согласие", "Клиент дал добро слушать (явно «ладно/слушаю» или вёл реальный диалог без отказа)"],
          ["S2 · Оффер донесён", "Клиент услышал оффер и среагировал по сути (спросил/возразил/продолжил)"],
          ["S3 · Встреча", "Клиент СОГЛАСИЛСЯ на встречу (принял время, «договорились»)"],
          ["S4 · Квалификация", "Клиент ответил на квалифицирующие вопросы (объём базы, кто решает и т.п.)"],
        ]} />
      </Section>

      <Section n="4" title="Северная звезда: QMR (Qualified Meeting Rate)">
        <p className="mb-3">
          <b>QMR = квалифицированные встречи / состоявшиеся согласия (S1).</b>
          {nsm != null && <> Сейчас <b>{pct(nsm, 2)}</b>.</>}
        </p>
        <ul className="list-disc pl-5 space-y-1.5 text-sm">
          <li><b>Почему не «встречи»:</b> сырой счётчик встреч бот «гонит» мусором (пустые/нерелевантные встречи),
            которые убивают экономику отдела продаж. Квалификация — встроенный фильтр качества.</li>
          <li><b>Почему знаменатель S1, а не все набранные номера:</b> так мы отделяем качество промпта от проблем
            дозвона. Дозвон живёт отдельной метрикой (Reachability).</li>
          <li><b>Почему рядом нужны варианты:</b> на холодном аутбаунде QMR мал по природе. Поэтому показываем
            <i> Meeting Rate</i> (встречи/S1), <i>QMR без дисквалифицированных</i> и <i>per-dial</i> (с «подмешанным» дозвоном).</li>
        </ul>
      </Section>

      <Section n="5" title="Метрическое дерево (а не плоский список)">
        <p className="mb-3">Метрики связаны причинно — это позволяет от «что упало» дойти до «что чинить»:</p>
        <div className="rounded-[var(--radius-md)] bg-[var(--color-bg-card-hover)] p-4 text-sm space-y-2">
          <TreeRow a="NSM (QMR)" b="главная цель" />
          <TreeRow a="↳ Драйверы: 4 переходные конверсии" b="каждая = 1 блок промпта (опенер/оффер/закрытие/квалификация)" />
          <TreeRow a="↳ Диагностика: паттерны, возражения, voice" b="почему конверсия такая" />
          <TreeRow a="↳ Guardrails / контр-метрики" b="что нельзя сломать ради роста" />
        </div>
      </Section>

      <Section n="6" title="Сигнал → блок промпта → рычаг → метрика">
        <p className="mb-3">Сердце пайплайна коррекций: как наблюдение превращается в правку.</p>
        <Table head={["Сигнал", "Блок", "Рычаг", "Guardrail"]} rows={[
          ["Низкое согласие / отвал на приветствии", "Опенер", "Короче, ценность вперёд, мягкое согласие", "Жалобы, early-drop"],
          ["Монолог, высокая доля речи бота", "Оффер", "Боль→выгода→1 факт, чек-ин-вопрос", "AHT"],
          ["Согласие есть, встреч мало", "Закрытие", "Альтернативное закрытие, лестница отступления", "Давление, дисквалификация"],
          ["Встречи без квалификации", "Квалификация", "Вплести 1–2 вопроса в контекст встречи", "AHT, качество встреч"],
          ["«Не слышу / алло / что?»", "—", "ЭСКАЛАЦИЯ в телефонию/ASR", "—"],
        ]} />
      </Section>

      <Section n="7" title="Приоритизация: opportunity sizing">
        <p>
          Бэклог ранжируется не по «самой низкой конверсии», а по <b>ожидаемому росту NSM с учётом прохождения
          вниз по воронке</b>. Починка не-связывающей стадии просто загоняет больше людей в ту же дыру ниже.
          Формула: <code className="text-xs">Δ ≈ объём_входа × достижимый_прирост × ∏(конверсии ниже) / база</code>,
          далее делится на усилие. Поэтому узкое место (по абсолютным потерям) и приоритет №1 в бэклоге могут различаться — и это правильно.
        </p>
      </Section>

      <Section n="8" title="Замкнутый цикл коррекций">
        <div className="flex flex-wrap items-center gap-2 text-sm">
          {["Измерил (метрики)", "Диагностировал (сигналы)", "Гипотеза (бэклог)", "Проверил A/B", "Раскатил / откатил"].map((s, i, arr) => (
            <span key={i} className="flex items-center gap-2">
              <span className="rounded-full bg-[var(--color-accent-subtle)] text-[var(--color-accent)] px-3 py-1 text-xs font-medium">{s}</span>
              {i < arr.length - 1 && <ArrowRight size={14} className="text-[var(--color-ink-muted)]" />}
            </span>
          ))}
        </div>
      </Section>

      <Section n="9" title="Дизайн экспериментов">
        <ul className="list-disc pl-5 space-y-1.5 text-sm">
          <li><b>Единица — контакт</b> (не звонок): один телефон не должен попасть в обе ветки.</li>
          <li><b>Решающее правило</b> по NSM + guardrails: рост QMR не успех, если пробит хоть один guardrail (жалобы, дисквалификация, давление).</li>
          <li><b>MDE и выборка</b> рассчитаны на каждую конверсию (80% мощность, α=0.05) — см. карточки драйверов.</li>
          <li><b>Дисциплина множественных сравнений:</b> не тестировать 5 правок одновременно без поправки.</li>
          <li><b>Симпсон:</b> проверять сегменты (отрасль, время суток) — общий рост может скрывать падение в сегменте.</li>
          <li><b>Постоянный holdout</b> и качество как опережающий индикатор (с проверкой предиктивности).</li>
        </ul>
      </Section>

      <Section n="10" title="Voice-слой и что нужно доинструментовать">
        <p>
          Часть критичных голосовых сигналов <b>не извлекается из текста</b>: задержка до реплики (dead-air),
          перебивания (barge-in), ASR-confidence, просодия. Сейчас мы проксируем что можем (repair-rate,
          доля речи бота) и честно помечаем остальное на странице <b>«Техника»</b> с обоснованием, зачем это нужно.
          Это апгрейд контракта данных у источника.
        </p>
      </Section>

      <Section n="11" title="LLM-анализ и failsafe">
        <p>
          Точная разметка стадий и сигналов делается <b>LLM</b> (Z.ai/GLM → Anthropic как fallback) на содержательных
          диалогах. Если модель недоступна, включается <b>детерминированный failsafe</b> на правилах — он считает те
          же метрики по тому же контракту, просто грубее. Баннер вверху всегда показывает, какой режим активен.
        </p>
      </Section>

      <Section n="12" title="A/B сегодня → мультиагентный отдел холодных продаж завтра">
        <p className="mb-3">
          Сегодняшний A/B-тест — это сравнение двух вариантов промпта. Это частный случай (2 агента, 1 раунд).
          В будущем тестирование перерастает в <b>непрерывный турнир агентов</b>: пул вариантов соревнуется на живом
          трафике, лучшие размножаются, а <b>ценные приёмы перетекают между агентами</b> через общий банк знаний.
          Это превращает «один бот» в самообучающийся <b>агентский отдел холодных продаж</b>.
        </p>
        <div className="mb-3 grid grid-cols-1 sm:grid-cols-2 gap-2.5">
          {[
            ["Арена / Оркестратор", "Распределяет контакты между агентами (multi-armed bandit), ведёт лидерборд по NSM+guardrails, защищает holdout."],
            ["Пул агентов", "Варианты промптов/стратегий, в т.ч. специализация по сегментам/отраслям (опт, металл, услуги…)."],
            ["Оценщик", "LLM-судья + метрики: считает QMR, качество диалога и guardrails по каждому агенту, отсекает «мусорные встречи»."],
            ["Селектор (эволюция)", "Bandit/генетика: размножает победителей, мутирует промпт, отсевает слабых. A/B = его простейший случай."],
            ["Банк знаний / память", "Победные опенеры, отработки возражений, инсайты CustDev — общий vector-store, из которого агенты заимствуют приёмы."],
            ["Шина обмена", "Агенты делятся успешными ходами: «приём X поднял S2→S3 в сегменте Y» расходится по пулу."],
          ].map(([t, d]) => (
            <div key={t} className="rounded-[var(--radius-md)] border border-[var(--color-border)] bg-[var(--color-bg-card)] p-3">
              <div className="text-sm font-medium text-[var(--color-ink)]">{t}</div>
              <div className="text-[11px] leading-relaxed text-[var(--color-ink-tertiary)] mt-0.5">{d}</div>
            </div>
          ))}
        </div>
        <p className="text-sm">
          <b>Дисциплина та же, что и в разделе 9:</b> единица — контакт, решающее правило по NSM + guardrails,
          постоянный holdout, контроль Симпсона по сегментам. Турнир лишь автоматизирует цикл «измерил →
          поправил → проверил» и масштабирует его на десятки конкурирующих стратегий одновременно.
        </p>
      </Section>
    </div>
  );
}

function Section({ n, title, children }: { n: string; title: string; children: ReactNode }) {
  return (
    <section className="scroll-mt-6">
      <h2 className="mb-2 text-lg flex items-baseline gap-2" style={{ fontFamily: "var(--font-display)" }}>
        <span className="text-[var(--color-accent)] text-sm stat-num">{n}</span>{title}
      </h2>
      <div className="text-sm leading-relaxed text-[var(--color-ink-secondary)]">{children}</div>
    </section>
  );
}

function LayerCard({ icon, title, body, foot, tone }: { icon: ReactNode; title: string; body: string; foot: string; tone: "ok" | "accent" }) {
  return (
    <div className={`rounded-[var(--radius-xl)] border p-4 ${tone === "ok" ? "border-[var(--color-band-ok)]/30 bandbg-ok" : "border-[var(--color-accent)]/25 bg-[var(--color-accent-bg)]"}`}>
      <div className="flex items-center gap-2 mb-1.5 font-medium text-[var(--color-ink)]">{icon}{title}</div>
      <p className="text-[13px] leading-relaxed text-[var(--color-ink-secondary)]">{body}</p>
      {foot && <p className="mt-2 text-xs stat-num text-[var(--color-ink-tertiary)]">{foot}</p>}
    </div>
  );
}

function Table({ head, rows }: { head?: string[]; rows: string[][] }) {
  return (
    <div className="overflow-hidden rounded-[var(--radius-md)] border border-[var(--color-border)]">
      <table className="w-full text-sm">
        {head && (
          <thead><tr className="bg-[var(--color-bg-card-hover)] text-[10px] uppercase tracking-wider text-[var(--color-ink-tertiary)]">
            {head.map((h) => <th key={h} className="text-left px-3 py-2 font-medium">{h}</th>)}
          </tr></thead>
        )}
        <tbody>
          {rows.map((r, i) => (
            <tr key={i} className="border-t border-[var(--color-border)]">
              {r.map((c, j) => (
                <td key={j} className={`px-3 py-2 align-top ${j === 0 ? "font-medium text-[var(--color-ink)] whitespace-nowrap" : "text-[var(--color-ink-secondary)]"}`}>{c}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function TreeRow({ a, b }: { a: string; b: string }) {
  return (
    <div className="flex flex-col sm:flex-row sm:items-baseline sm:gap-2">
      <span className="font-medium text-[var(--color-ink)]">{a}</span>
      <span className="text-xs text-[var(--color-ink-tertiary)]">— {b}</span>
    </div>
  );
}
