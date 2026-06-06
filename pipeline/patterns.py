"""Psychological pattern catalog for the Botamin sales bot — single source of truth.

Adapted from a 167-pattern sales-psychology catalog (prior project) and CURATED to
~66 patterns that actually occur in a short B2B cold call run by a voice BOT. We
keep the original PSY-* ids and the 15-category structure so the catalog stays
recognizable and extensible to the full 167 later.

WHY THIS MODULE EXISTS:
  - The LLM analyzer (pipeline/llm/analyze.py) lists this catalog in its prompt and
    may ONLY assign ids from here (conservative, evidence-grounded detection).
  - The deterministic aggregator (pipeline/diagnostics.py) looks up every detected
    id here to get name / polarity / impact / weight / prompt_block. So adding a
    pattern in ONE place makes it flow end-to-end (detection → aggregation → UI).

DESIGN:
  - `prompt_block` ties each pattern to the funnel stage the backlog optimizes
    (opener S0→S1, offer S1→S2, closing S2→S3, qualification S3→S4, context).
    For the 10 legacy ids we preserve their original blocks so the backlog grouping
    does not regress.
  - The LLM never produces COUNTS — it only says which patterns are present, with a
    verbatim quote. Frequencies/lift are computed deterministically downstream.
"""
from __future__ import annotations

# impact → numeric weight used by diagnostics.audit_bot_patterns and backlog ranking
IMPACT_WEIGHT = {"critical": 3.0, "high": 2.0, "medium": 1.0, "low": 0.5}

# Curated catalog. id -> {name, polarity, impact, category, prompt_block}
# polarity: positive (helps the sale) | negative (hurts the sale)
CATALOG: dict[str, dict] = {
    # ── 1. Раппорт и доверие (→ opener) ─────────────────────────────────────
    "PSY-004": {"name": "Эмпатическое присоединение", "polarity": "positive", "impact": "high", "category": "Раппорт", "prompt_block": "opener"},
    "PSY-008": {"name": "Тёплое открытие (не с продажи)", "polarity": "positive", "impact": "medium", "category": "Раппорт", "prompt_block": "opener"},
    "PSY-010": {"name": "Запрос разрешения в опенере", "polarity": "positive", "impact": "high", "category": "Раппорт", "prompt_block": "opener"},
    "PSY-011": {"name": "Питч в лоб в опенере (без согласия)", "polarity": "negative", "impact": "critical", "category": "Раппорт", "prompt_block": "opener"},
    "PSY-015": {"name": "Роботизированная речь без интонации", "polarity": "negative", "impact": "high", "category": "Раппорт", "prompt_block": "opener"},

    # ── 2. Контроль фрейма (→ opener) ───────────────────────────────────────
    "PSY-016": {"name": "Фрейм эксперта/консультанта", "polarity": "positive", "impact": "critical", "category": "Фрейм", "prompt_block": "opener"},
    "PSY-018": {"name": "Рефрейминг возражения в аргумент", "polarity": "positive", "impact": "critical", "category": "Фрейм", "prompt_block": "closing"},
    "PSY-023": {"name": "Фрейм просителя (снизу)", "polarity": "negative", "impact": "critical", "category": "Фрейм", "prompt_block": "opener"},
    "PSY-026": {"name": "Фрейм извинения («простите за беспокойство»)", "polarity": "negative", "impact": "high", "category": "Фрейм", "prompt_block": "opener"},

    # ── 3. Влияние по Чалдини (→ offer) ─────────────────────────────────────
    "PSY-027": {"name": "Соц. доказательство (конкретное имя клиента)", "polarity": "positive", "impact": "critical", "category": "Влияние", "prompt_block": "offer"},
    "PSY-028": {"name": "Соц. доказательство (число клиентов)", "polarity": "positive", "impact": "high", "category": "Влияние", "prompt_block": "offer"},
    "PSY-032": {"name": "Взаимность: ценность вперёд (бесплатно)", "polarity": "positive", "impact": "critical", "category": "Влияние", "prompt_block": "offer"},
    "PSY-036": {"name": "Последовательность: серия мини-да", "polarity": "positive", "impact": "critical", "category": "Влияние", "prompt_block": "offer"},
    "PSY-039": {"name": "Давление без раппорта", "polarity": "negative", "impact": "critical", "category": "Влияние", "prompt_block": "offer"},

    # ── 4. Вопросы и выявление (→ offer) ────────────────────────────────────
    "PSY-042": {"name": "Открытый вопрос", "polarity": "positive", "impact": "high", "category": "Вопросы", "prompt_block": "offer"},
    "PSY-044": {"name": "Проблемный вопрос (SPIN)", "polarity": "positive", "impact": "high", "category": "Вопросы", "prompt_block": "offer"},
    "PSY-045": {"name": "Извлекающий вопрос о последствиях (SPIN)", "polarity": "positive", "impact": "critical", "category": "Вопросы", "prompt_block": "offer"},
    "PSY-047": {"name": "Альтернативный вопрос (выбор из двух «да»)", "polarity": "positive", "impact": "critical", "category": "Вопросы", "prompt_block": "closing"},
    "PSY-053": {"name": "Допрос (5+ вопросов подряд)", "polarity": "negative", "impact": "high", "category": "Вопросы", "prompt_block": "offer"},
    "PSY-055": {"name": "Отсутствие вопросов (чистый монолог)", "polarity": "negative", "impact": "critical", "category": "Вопросы", "prompt_block": "offer"},

    # ── 5. Эмоциональный интеллект (→ context) ──────────────────────────────
    "PSY-057": {"name": "Считывание интереса (углубление темы)", "polarity": "positive", "impact": "high", "category": "Эмоции", "prompt_block": "context"},
    "PSY-058": {"name": "Считывание раздражения (смена тактики)", "polarity": "positive", "impact": "critical", "category": "Эмоции", "prompt_block": "context"},
    "PSY-060": {"name": "Эмпатия к возражению (валидация чувств)", "polarity": "positive", "impact": "high", "category": "Эмоции", "prompt_block": "closing"},
    "PSY-064": {"name": "Эмоциональная глухота к раздражению", "polarity": "negative", "impact": "critical", "category": "Эмоции", "prompt_block": "context"},
    "PSY-067": {"name": "Манипулятивный страх (запугивание)", "polarity": "negative", "impact": "high", "category": "Эмоции", "prompt_block": "offer"},

    # ── 6. НЛП и язык (→ offer) ─────────────────────────────────────────────
    "PSY-068": {"name": "Пресуппозиция («когда мы встретимся…»)", "polarity": "positive", "impact": "critical", "category": "НЛП", "prompt_block": "closing"},
    "PSY-073": {"name": "Yes-set (серия очевидных «да»)", "polarity": "positive", "impact": "high", "category": "НЛП", "prompt_block": "offer"},
    "PSY-079": {"name": "Слова-ослабители («может быть», «как бы»)", "polarity": "negative", "impact": "high", "category": "НЛП", "prompt_block": "offer"},
    "PSY-081": {"name": "Жаргон без перевода для непрофильного ЛПР", "polarity": "negative", "impact": "high", "category": "НЛП", "prompt_block": "offer"},

    # ── 7. Психология возражений (→ closing) ────────────────────────────────
    "PSY-082": {"name": "Feel-Felt-Found (нормализация через опыт других)", "polarity": "positive", "impact": "critical", "category": "Возражения", "prompt_block": "offer"},
    "PSY-083": {"name": "Бумеранг: возражение → аргумент за встречу", "polarity": "positive", "impact": "critical", "category": "Возражения", "prompt_block": "closing"},
    "PSY-084": {"name": "Изоляция возражения («это единственное?»)", "polarity": "positive", "impact": "high", "category": "Возражения", "prompt_block": "closing"},
    "PSY-091": {"name": "Спор с клиентом («нет, вы не правы»)", "polarity": "negative", "impact": "critical", "category": "Возражения", "prompt_block": "closing"},
    "PSY-094": {"name": "Игнорирование возражения", "polarity": "negative", "impact": "critical", "category": "Возражения", "prompt_block": "offer"},
    "PSY-095": {"name": "Преждевременная сдача («пришлю на почту»)", "polarity": "negative", "impact": "critical", "category": "Возражения", "prompt_block": "closing"},

    # ── 8. Техники закрытия (→ closing) ─────────────────────────────────────
    "PSY-096": {"name": "Альтернативное закрытие («вторник или среда?»)", "polarity": "positive", "impact": "critical", "category": "Закрытие", "prompt_block": "closing"},
    "PSY-097": {"name": "Презумптивное закрытие (как свершившийся факт)", "polarity": "positive", "impact": "critical", "category": "Закрытие", "prompt_block": "closing"},
    "PSY-101": {"name": "Снятие давления («встреча ни к чему не обязывает»)", "polarity": "positive", "impact": "critical", "category": "Закрытие", "prompt_block": "closing"},
    "PSY-102": {"name": "Фиксация договорённости (дата/время/канал)", "polarity": "positive", "impact": "critical", "category": "Закрытие", "prompt_block": "closing"},
    "PSY-106": {"name": "Нет попытки закрытия / нет CTA", "polarity": "negative", "impact": "critical", "category": "Закрытие", "prompt_block": "closing"},
    "PSY-108": {"name": "Пассивное закрытие («надумаете — звоните»)", "polarity": "negative", "impact": "critical", "category": "Закрытие", "prompt_block": "closing"},
    "PSY-109": {"name": "Размытый next step («как-нибудь перезвоню»)", "polarity": "negative", "impact": "high", "category": "Закрытие", "prompt_block": "closing"},
    "PSY-110": {"name": "Избыточное давление после отказа", "polarity": "negative", "impact": "high", "category": "Закрытие", "prompt_block": "closing"},

    # ── 9. Сторителлинг (→ offer) ───────────────────────────────────────────
    "PSY-111": {"name": "Кейс-история (конкретный пример с деталями)", "polarity": "positive", "impact": "critical", "category": "Сторителлинг", "prompt_block": "offer"},
    "PSY-112": {"name": "Отраслевой кейс (из отрасли клиента)", "polarity": "positive", "impact": "critical", "category": "Сторителлинг", "prompt_block": "offer"},
    "PSY-116": {"name": "Сухое перечисление услуг без истории", "polarity": "negative", "impact": "high", "category": "Сторителлинг", "prompt_block": "offer"},

    # ── 10. Темп и структура (→ context/offer) ──────────────────────────────
    "PSY-120": {"name": "Оптимальный хронометраж (не затянуто)", "polarity": "positive", "impact": "high", "category": "Темп", "prompt_block": "context"},
    "PSY-123": {"name": "Своевременный переход к закрытию", "polarity": "positive", "impact": "critical", "category": "Темп", "prompt_block": "closing"},
    "PSY-124": {"name": "Затянутый монолог-питч (>60 слов)", "polarity": "negative", "impact": "critical", "category": "Темп", "prompt_block": "offer"},

    # ── 11. Привратник (→ opener) — у бота редко, держим минимум ─────────────
    "PSY-130": {"name": "Обход привратника через конкретику (имя ЛПР)", "polarity": "positive", "impact": "critical", "category": "Привратник", "prompt_block": "opener"},
    "PSY-133": {"name": "Раскрытие коммерческой цели секретарю", "polarity": "negative", "impact": "critical", "category": "Привратник", "prompt_block": "opener"},

    # ── 12. Персонализация (→ opener) ───────────────────────────────────────
    "PSY-140": {"name": "Технологическая привязка (упомянул стек клиента)", "polarity": "positive", "impact": "critical", "category": "Персонализация", "prompt_block": "opener"},
    "PSY-142": {"name": "Нулевая подготовка (шаблонный звонок)", "polarity": "negative", "impact": "high", "category": "Персонализация", "prompt_block": "opener"},

    # ── 13. Позиционирование ценности (→ offer) ─────────────────────────────
    "PSY-145": {"name": "Бизнес-язык (риски → деньги/время)", "polarity": "positive", "impact": "critical", "category": "Ценность", "prompt_block": "offer"},
    "PSY-146": {"name": "ROI-аргумент (цена решения vs цена проблемы)", "polarity": "positive", "impact": "critical", "category": "Ценность", "prompt_block": "offer"},
    "PSY-148": {"name": "Бесплатный якорь (демо/аудит без обязательств)", "polarity": "positive", "impact": "critical", "category": "Ценность", "prompt_block": "offer"},
    "PSY-151": {"name": "Feature dump (перечисление функций)", "polarity": "negative", "impact": "critical", "category": "Ценность", "prompt_block": "offer"},
    "PSY-152": {"name": "Абстрактная ценность без конкретики", "polarity": "negative", "impact": "high", "category": "Ценность", "prompt_block": "offer"},

    # ── 14. Лестница обязательств (→ closing) ───────────────────────────────
    "PSY-154": {"name": "Микро-согласие на разговор", "polarity": "positive", "impact": "high", "category": "Обязательства", "prompt_block": "opener"},
    "PSY-156": {"name": "Согласие на ценность («было бы полезно?»)", "polarity": "positive", "impact": "critical", "category": "Обязательства", "prompt_block": "offer"},
    "PSY-157": {"name": "Согласие на встречу", "polarity": "positive", "impact": "critical", "category": "Обязательства", "prompt_block": "closing"},
    "PSY-159": {"name": "Прыжок через ступени (сразу к встрече)", "polarity": "negative", "impact": "high", "category": "Обязательства", "prompt_block": "closing"},

    # ── 15. Мета-паттерны (→ context) ───────────────────────────────────────
    "PSY-161": {"name": "Адаптивность (смена стратегии по реакциям)", "polarity": "positive", "impact": "critical", "category": "Мета", "prompt_block": "context"},
    "PSY-162": {"name": "Множественные попытки закрытия (не повторы)", "polarity": "positive", "impact": "critical", "category": "Мета", "prompt_block": "closing"},

    # ── Голос/связь (бот-специфика, не из исходного каталога) (→ context) ────
    "PSY-200": {"name": "ASR-петля (бот повторяет один вопрос)", "polarity": "negative", "impact": "high", "category": "Голос/ASR", "prompt_block": "context"},
    "PSY-201": {"name": "Глухота к проблеме связи («не слышу» — бот питчит)", "polarity": "negative", "impact": "critical", "category": "Голос/ASR", "prompt_block": "context"},
}

# Stable category order for grouping in the prompt + UI.
CATEGORY_ORDER = [
    "Раппорт", "Фрейм", "Влияние", "Вопросы", "Эмоции", "НЛП", "Возражения",
    "Закрытие", "Сторителлинг", "Темп", "Привратник", "Персонализация",
    "Ценность", "Обязательства", "Мета", "Голос/ASR",
]

ALLOWED_IDS = set(CATALOG.keys())


def pattern_meta(pattern_id: str) -> dict:
    """Return catalog metadata for an id, or a safe default for unknown ids."""
    return CATALOG.get(pattern_id, {
        "name": pattern_id, "polarity": "negative", "impact": "medium",
        "category": "Прочее", "prompt_block": "context",
    })


def weight_of(pattern_id: str) -> float:
    return IMPACT_WEIGHT.get(pattern_meta(pattern_id)["impact"], 1.0)


def catalog_for_prompt() -> str:
    """Compact RU catalog block for the LLM system prompt, grouped by category.

    One line per pattern: `PSY-XXX [+/-] name`. The sign encodes polarity so the
    model needn't guess it. Names are descriptive enough to act as detection hints,
    keeping the prompt token-lean.
    """
    by_cat: dict[str, list[str]] = {c: [] for c in CATEGORY_ORDER}
    for pid in sorted(CATALOG):
        m = CATALOG[pid]
        by_cat.setdefault(m["category"], [])
        sign = "+" if m["polarity"] == "positive" else "−"
        by_cat[m["category"]].append(f"  {pid} [{sign}] {m['name']}")
    out = []
    for cat in CATEGORY_ORDER:
        lines = by_cat.get(cat)
        if lines:
            out.append(f"{cat}:")
            out.extend(lines)
    return "\n".join(out)
