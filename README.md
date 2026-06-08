# Botamin BI

> **Аналитика голосового агента продаж.** Сырые звонки → детерминированный Python-пайплайн + один проход LLM → интерактивный React-дашборд.
>
> **Принцип:** _Числа считает код, смысл понимает ИИ._

[![Deploy](https://github.com/Gorby200/Botamin-BI/actions/workflows/deploy.yml/badge.svg)](https://github.com/Gorby200/Botamin-BI/actions)
![Python](https://img.shields.io/badge/python-3.13-3776AB?logo=python&logoColor=white)
![React](https://img.shields.io/badge/react-19-61DAFB?logo=react&logoColor=black)
![Vite](https://img.shields.io/badge/vite-8-646CFF?logo=vite&logoColor=white)
![Tailwind](https://img.shields.io/badge/tailwind-v4-06B6D4?logo=tailwindcss&logoColor=white)
![Data](https://img.shields.io/badge/режим-презентация-EAB308)

**Демо:** https://gorby200.github.io/Botamin-BI/

---

## Что это

Botamin BI превращает выгрузку звонков голосового бота в управленческую картину: где теряется воронка, насколько качественно бот **ведёт** разговор, что говорят клиенты (CustDev) и какие гипотезы тестировать первыми.

Ключевая идея — **гибридный пайплайн**:

| Кто считает | Что | Почему так |
|---|---|---|
| **Код (детерминированно)** | Вся воронка, конверсии, распределения, длительности, частоты паттернов/возражений, атрибуция потерь, итоговый балл качества и грейд, Outcome, Gap | Цифры нельзя «отдавать на фантазию» модели — они должны быть воспроизводимы и проверяемы |
| **LLM (один проход на диалог)** | Достигнутые стадии (с цитатой клиента как доказательством), психологические паттерны, слои качества V4 (Macro/Micro/Overlap, 0–10), CustDev / Product-Intelligence / JTBD, рекомендации | Это интерпретация смысла — то, где ценен «здравый смысл» модели |

LLM **никогда** не выдаёт счётчики и проценты — только суждения, всегда подкреплённые дословной цитатой клиента. Арифметику (итог качества, грейд A–F, Outcome из «дальше всего достигнутой стадии», Gap = качество − результат) делает Python.

### Результаты на текущем датасете

> Период **25–29 мая 2026**, **11 486** звонков. LLM-разбор: **Z.ai / GLM**, режим `focus` — **261** содержательный диалог.

```
Воронка (по словам клиента):
  S0 Контакт ......... 873   состоявшихся разговоров
  S1 Согласие ........ 355
  S2 Оффер донесён ... 138
  S3 Встреча ......... 47
  S4 Квалификация .... 13

NSM · QMR (квалиф. встречи ÷ согласия) ... 3.66 %
Качество ведения (V4) .................... 4.09 / 10
Результат (Outcome) ...................... 2.09 / 10
Gap (качество − результат) ............... +2.0  → теряем на закрытии/базе, а не в навыке
```

---

## Архитектура

```
data/raw.csv ─► ingest ─► _extract_features ─► classify_dialogue  (ДЕТЕРМИНИРОВАННЫЙ failsafe — всегда)
                                                      │  единый контракт диалога
                                                      ▼
              ┌─ LLM включён и scope ≠ off ─► run_analysis()  ◄── ОДИН проход на отобранный диалог (кэш на диске)
              │     один богатый промпт = стадии + 66 паттернов + V4-качество + product_intel + синтез
              │     _normalize() → тот же контракт (+quality, +product_intel); арифметику считает Python
              ▼
   features[i].analysis  (детерминированно для неотобранных, LLM для отобранных — ОДИН и тот же контракт)
                                                      ▼
   metrics.compute_metrics ........ воронка / reach / NSM / качество / guardrails  (детерминированно)
   diagnostics.audit_bot_patterns . частоты паттернов + lift                        (каталог из patterns.py)
   custdev.build_custdev .......... REDUCE product_intel → реальные счётчики         (детерминированно)
                                                      ▼
              frontend/public/data/{dashboard,custdev,backlog,research}.json + calls/page_*.json
                                                      ▼
                          React 19 SPA (Vite · Tailwind v4 · Recharts · HashRouter)
```

**Деплой — статический, без обращения к LLM на пуше:**

```
[локально] python -m pipeline ──► генерим JSON ──► git commit (JSON + raw.csv)
                                                        │
                                                        ▼ push
[GitHub Actions] npm run build ──► статический dist/ ──► GitHub Pages
   ⚠ пайплайн запускается ТОЛЬКО вручную (workflow_dispatch), на обычный push LLM не дёргается
```

Это сознательное решение: данные предрассчитываются на машине разработчика и едут в репозитории, а CI лишь собирает статику. Так мы не упираемся в rate-limit провайдера при каждом пуше и деплой остаётся быстрым и дешёвым.

---

## Быстрый старт

**Требования:** Python 3.13+, Node.js 20+.

```bash
git clone https://github.com/Gorby200/Botamin-BI.git
cd Botamin-BI

# 1. Python-окружение
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # macOS / Linux
pip install -r requirements.txt

# 2. Фронтенд
cd frontend && npm install && cd ..

# 3. Ключи LLM (опционально — без них работает детерминированный режим)
cp .env.example .env            # затем впишите ключи вручную

# 4. Сгенерировать данные локально
python -m pipeline --file data/raw.csv --llm-scope focus

# 5. Запустить дашборд
cd frontend && npm run dev      # http://localhost:5173
```

### Глубина LLM-разбора (`--llm-scope`)

| Scope | Что разбирает | Когда |
|---|---|---|
| `off` | ничего — только детерминированные правила | без ключа / отладка / CI |
| `focus` | содержательные диалоги (≥ 3 реплик клиента) | **по умолчанию** — лучший баланс |
| `full` | все состоявшиеся разговоры | полное покрытие |
| `sample` | случайная выборка `LLM_SAMPLE_SIZE` | быстрая калибровка |

> Переключатель «Охват» в шапке дашборда и в Настройках показывает текущий режим. Кнопка «Пересчитать звонки» в Настройках триггерит GitHub Actions (`workflow_dispatch`) — единственный честный способ для статического сайта запросить пересчёт.

---

## Страницы

| Страница | Что показывает |
|---|---|
| **Продукт** (Overview) | KPI, NSM, полоса конверсии S0→S4 с подсветкой узкого места |
| **Воронка** | Стадии с атрибуцией потерь: контекст (связь/ASR) vs управляемое (промпт) |
| **Голос. агент** | Качество ведения диалога (V4): Macro/Micro/Overlap, Outcome, Gap |
| **Техника** | Связь, ASR, инструментовка и пробелы телеметрии |
| **Звонки** | Просмотр диалогов: транскрипт, стадии, паттерны с цитатами, возражения, product-intel, рекомендации |
| **CustDev** | Голос клиента: боли, JTBD, конкуренты, ценовые сигналы — с дословными цитатами |
| **Бэклог** | Приоритизированные гипотезы и дизайн A/B |
| **Отчёт клиенту** | Сводка + выгрузка в PDF |
| **Методика** | Почему так считаем (NSM, V4, атрибуция потерь) |
| **Настройки** | Пороги метрик, охват LLM, пересчёт |

---

## Стек

- **Бэкенд:** Python 3.13, pandas. LLM: **Z.ai / GLM (`glm-4.6`)** основной + **Anthropic Claude** как fallback. Низкая конкурентность (2 соединения), кэш на диске на каждый диалог, salvage-парсинг JSON, экспоненциальный backoff.
- **Фронтенд:** React 19, Vite 8, TypeScript, Tailwind CSS v4, Recharts, lucide-react, HashRouter (устойчив к подпути GitHub Pages).
- **Данные:** постраничное хранилище (≈50 звонков на файл) — десятки `page_*.json` вместо тысяч файлов, дружелюбно к кэшу браузера.

---

## Структура проекта

```
Botamin-BI/
├── .github/workflows/deploy.yml   # CI: pipeline только на workflow_dispatch; сборка статики на push
├── config/thresholds.yaml         # пороги метрик (бэкенд)
├── data/raw.csv                   # датасет (в репозитории — режим презентации)
├── pipeline/
│   ├── __main__.py                # точка входа: python -m pipeline
│   ├── build.py                   # оркестрация: features → analysis → метрики → JSON
│   ├── ingest.py                  # загрузка CSV/Sheets
│   ├── stages.py                  # детерминированная классификация стадий (failsafe)
│   ├── patterns.py                # каталог из 66 психологических паттернов (единый источник)
│   ├── methodology.py             # V4-рубрика + арифметика качества/Outcome/Gap
│   ├── metrics.py                 # воронка / reach / NSM / guardrails
│   ├── diagnostics.py             # аудит паттернов (частоты + lift)
│   ├── custdev.py                 # REDUCE product_intel → CustDev с реальными счётчиками
│   ├── profile.py                 # профилирование данных
│   ├── config.py                  # настройки и загрузка .env
│   └── llm/
│       ├── client.py              # клиент Z.ai/Anthropic (concurrency=2, backoff)
│       ├── analyze.py             # ОДИН батчевый проход на диалог + кэш + repair JSON
│       └── orchestrator.py        # отбор диалогов + интеграция в пайплайн
├── frontend/
│   ├── public/data/               # сгенерированный JSON (коммитится — статический деплой)
│   └── src/
│       ├── App.tsx                # роутинг (HashRouter) + шапка
│       ├── pages/                 # страницы дашборда
│       ├── components/            # переиспользуемый UI (ScopeSelector, AnalysisBanner, …)
│       ├── thresholds.ts          # логика порогов и бэндов
│       ├── format.ts · hooks.ts · types.ts
│       └── index.css              # дизайн-система (Hanken Grotesk)
├── .env.example                   # шаблон переменных окружения
├── requirements.txt · build.sh · Makefile
├── DEPLOYMENT.md                  # подробный гайд по деплою
└── README.md
```

---

## Безопасность и данные

- **Ключи API** вписываются вручную в `.env` (в `.gitignore`, никогда не коммитится). Для CI — GitHub Secrets. В коде ключей нет.
- **Токен GitHub** для кнопки «Пересчитать» хранится только в `localStorage` браузера и отправляется только на `api.github.com`.
- **`data/raw.csv` и `frontend/public/data/**` содержат реальные транскрипты звонков.** Они коммитятся осознанно — это **режим презентации**, чтобы датасет ехал с репозиторием и сайт собирался без обращения к LLM. ⚠ **Держите репозиторий приватным**, если данные чувствительны; для продакшена выносите данные из репозитория.

---

## Документация

- **[DEPLOYMENT.md](DEPLOYMENT.md)** — подробный деплой и эксплуатация.

---

_Botamin BI — числа считает код, смысл понимает ИИ._
