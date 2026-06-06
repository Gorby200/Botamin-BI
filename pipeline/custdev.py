"""CustDev insight extraction from call transcripts.

The PO wants a "voice of the customer" page: what valuable things did we hear in
the calls? This is a lightweight, continuously-runnable CustDev engine built as a
GROUNDED MAP-REDUCE so that the numbers stay trustworthy:

  MAP   (LLM, per call, cached): read each transcript THROUGH an editable research
        lens and return themed insights, each backed by a VERBATIM client quote.
        The model extracts *meaning* and *quotes* — it never invents statistics.

  REDUCE (pure Python): group insights by category, count REAL occurrences,
        de-duplicate quotes, and emit the exact same contract the deterministic
        failsafe produces. Counts are computed by us, not guessed by the model.

  FAILSAFE (deterministic): when no API key is configured, cluster client
        utterances into the same categories by keyword, so the page always works.

Because both paths emit an identical `custdev.json` shape, the React page is
source-agnostic; only the `mode` field tells the analyst which engine ran.

Output (custdev.json) feeds a page that also lets the analyst live-filter quotes by
their own topic keywords.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
from pathlib import Path

import pandas as pd

from pipeline.config import settings

logger = logging.getLogger(__name__)

# Shared with the per-call LLM analyzer so a re-run over the same calls is free.
CACHE_DIR = Path(".llm_cache")


# The base CustDev lens. Editable on the page; passed to the LLM verbatim.
BASE_CUSTDEV_PROMPT = (
    "Мы ищем в разговорах с клиентами всё, что помогает улучшить продукт и продажи: "
    "боли и проблемы клиента, его задачи и сценарии, пожелания и недостающие функции, "
    "возражения и их настоящие причины, чувствительность к цене, кто и как принимает "
    "решение, какими конкурентами/альтернативами пользуются, уровень доверия к ИИ-боту. "
    "Цель — понять, что важного клиенты говорят, и превратить это в гипотезы для продукта и промпта."
)

# Insight categories. One curated `recommendation` per category gives the page a
# stable, CEO-readable "so what?", independent of per-call LLM wording. The
# `patterns` drive the deterministic keyword failsafe; the LLM is constrained to
# the same `key` space so the REDUCE step can label/recommend consistently.
CATEGORIES: list[dict] = [
    {
        "key": "pain", "label": "Боли и проблемы",
        "patterns": [r"проблем", r"не справля", r"тер[яе]ем", r"мало\s+(заяв|лид|клиент)",
                     r"не\s+хватает", r"текучк", r"не\s+успева", r"завал", r"руками\s+обзван", r"холодн.*тяжел"],
        "recommendation": "Зафиксировать боли как ценностные триггеры опенера/оффера — говорить на языке боли клиента.",
    },
    {
        "key": "wish", "label": "Пожелания и запрос функций",
        "patterns": [r"хотелось\s+бы", r"было\s+бы\s+(хорошо|здорово|удобно)", r"нам\s+нужн",
                     r"а\s+можно\s+ли", r"а\s+вы\s+(умеете|можете|делаете)", r"хочу\s+чтобы",
                     r"интересно\s+было\s+бы", r"не\s+хватает\s+функц", r"а\s+есть\s+ли"],
        "recommendation": "Кандидаты в product backlog: повторяющиеся запросы — сигнал к новой функции/интеграции.",
    },
    {
        "key": "competitor", "label": "Конкуренты и альтернативы",
        "patterns": [r"уже\s+(использу|пользу|работа|купил)", r"у\s+нас\s+есть\s+\w+", r"пробовали",
                     r"конкурент", r"другой\s+(сервис|вендор|подрядчик)", r"свой\s+(отдел|колл-?центр|обзвон)"],
        "recommendation": "Собрать карту альтернатив и отстройку: чем мы лучше того, что у клиента уже есть.",
    },
    {
        "key": "pricing", "label": "Цена и бюджет",
        "patterns": [r"сколько\s+стоит", r"дорого", r"\bцен[аыу]\b", r"бюджет", r"по\s+деньгам", r"окуп"],
        "recommendation": "Тестировать раннее снятие ценового страха и привязку цены к ROI/боли.",
    },
    {
        "key": "decision", "label": "Процесс принятия решения",
        "patterns": [r"не\s+я\s+решаю", r"передам", r"посовету", r"руководств", r"директор",
                     r"начальник", r"собственник", r"вынесу\s+на", r"согласу"],
        "recommendation": "Добавить ветку маршрутизации к ЛПР и заготовку «материалов для руководителя».",
    },
    {
        "key": "trust", "label": "Доверие к ИИ / скепсис",
        "patterns": [r"это\s+робот", r"вы\s+бот", r"искусственн", r"не\s+верю", r"развод",
                     r"\bспам\b", r"мошен", r"живой\s+человек"],
        "recommendation": "Проверить честную идентификацию бота и социальные доказательства (кейсы, цифры) рано в диалоге.",
    },
    {
        "key": "timing", "label": "Тайминг и сезонность",
        "patterns": [r"сейчас\s+не\s+врем", r"перезвон", r"\bпозже\b", r"в\s+сезон", r"после\s+(праздник|отпуск|нового)",
                     r"в\s+конце\s+(месяц|квартал)", r"не\s+сейчас"],
        "recommendation": "Тестировать перенос-договорённость (callback по конкретной дате) вместо потери контакта.",
    },
    {
        "key": "usecase", "label": "Сценарии и сегменты",
        "patterns": [r"мы\s+занимаем", r"у\s+нас\s+(b2b|b2c|оптов|рознич|производ|услуг)", r"наша\s+(ниша|сфера|отрасл)",
                     r"работаем\s+(в|с|по)", r"наши\s+клиент", r"специфик"],
        "recommendation": "Сегментировать промпт по отрасли/типу бизнеса — персонализация оффера повышает релевантность.",
    },
]

# Fast lookups built once from CATEGORIES.
_CAT_LABEL: dict[str, str] = {c["key"]: c["label"] for c in CATEGORIES}
_CAT_REC: dict[str, str] = {c["key"]: c["recommendation"] for c in CATEGORIES}
_CAT_ORDER: list[str] = [c["key"] for c in CATEGORIES]
ALLOWED_CATEGORIES: set[str] = set(_CAT_ORDER)

# "other" is a valid LLM output but has no curated meta — give it a home.
_CAT_LABEL["other"] = "Прочее"
_CAT_REC["other"] = "Разобрать вручную: не уложилось в типовые категории, но может содержать сигнал."

# Per-category cap on stored quotes to keep custdev.json lean for the SPA.
_MAX_QUOTES_PER_CATEGORY = 30
# How many top categories to surface in the executive summary.
_SUMMARY_TOP_N = 5


def _client_turns_text(turns: list[dict]) -> list[str]:
    return [t["text"] for t in turns if t.get("role") == "client"]


# ── LLM CustDev system prompt (the per-call extraction "lens") ──────────────
def llm_custdev_system(user_lens: str) -> str:
    """Build the per-call CustDev extraction prompt.

    Design (as a CustDev/product researcher + prompt engineer):
      - GROUNDING: insights must rest on the CLIENT's own words; the model quotes
        verbatim and is told not to infer from the bot's lines or invent anything.
      - CONSTRAINED TAXONOMY: category ∈ a fixed key set so the deterministic
        REDUCE step can attach stable labels/recommendations and compute real counts.
      - NO STATISTICS: the model never estimates frequencies/percentages — that is
        the pipeline's job. It only extracts meaning + evidence.
      - STRICT JSON: empty list when nothing valuable was said (most cold calls).
    """
    lens = (user_lens or BASE_CUSTDEV_PROMPT).strip()
    return (
        "Ты — продуктовый исследователь (CustDev) голосового AI-агента продаж Botamin. "
        "Тебе дают расшифровку ОДНОГО холодного звонка (реплики бота и клиента). "
        "Твоя задача — извлечь из слов КЛИЕНТА ценные продуктовые инсайты.\n\n"
        f"ФОКУС ИССЛЕДОВАНИЯ (через какую призму смотреть):\n{lens}\n\n"
        "ЖЕЛЕЗНЫЕ ПРАВИЛА:\n"
        "1. Опирайся ТОЛЬКО на слова клиента. Реплики бота — контекст, не источник инсайта.\n"
        "2. Каждый инсайт обязан иметь дословную цитату клиента (quote) — копируй точно, не перефразируй.\n"
        "3. Ничего не выдумывай. Нет ценного сигнала — верни пустой список (это норма для холодных звонков).\n"
        "4. Категория (category) — СТРОГО одно из значений:\n"
        "   pain — боль/проблема клиента;\n"
        "   wish — пожелание, запрос функции/интеграции;\n"
        "   competitor — конкурент/альтернатива/то, что уже используют;\n"
        "   pricing — цена, бюджет, окупаемость;\n"
        "   decision — кто и как принимает решение (ЛПР, согласование);\n"
        "   trust — доверие/скепсис к ИИ-боту;\n"
        "   timing — тайминг/сезонность/«не сейчас»;\n"
        "   usecase — отрасль, сегмент, специфика бизнеса;\n"
        "   other — ценное, но не попадает в категории выше.\n"
        "5. insight — краткая суть на языке продакта (1 фраза). recommendation — что с этим сделать "
        "(гипотеза для продукта или для промпта бота).\n"
        "6. Все поля пиши ТОЛЬКО на русском языке.\n\n"
        "ФОРМАТ ОТВЕТА — строго этот JSON-объект:\n"
        '{ "insights": [ '
        '{ "category": "pain", "insight": "...", "quote": "дословная цитата клиента", "recommendation": "..." } '
        "] }\n"
        'Если ничего ценного нет: { "insights": [] }'
    )


# ── MAP: per-call LLM extraction (cached, concurrency-limited) ──────────────
def _transcript_text(turns: list[dict]) -> str:
    out = []
    for t in turns:
        role = "Бот" if t.get("role") == "bot" else "Клиент" if t.get("role") == "client" else "?"
        out.append(f"{role}: {t.get('text', '')}")
    return "\n".join(out)


def _cache_key(lens: str, transcript: str, model: str) -> str:
    # Namespaced 'custdev:' so it never collides with analyze.py's per-call cache,
    # and keyed by the lens so editing the research focus re-extracts.
    payload = f"custdev:{model}\x00{lens}\x00{transcript}"
    return "cd_" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:21]


def _cache_get(key: str):
    p = CACHE_DIR / f"{key}.json"
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return None
    return None


def _cache_put(key: str, value) -> None:
    CACHE_DIR.mkdir(exist_ok=True)
    try:
        (CACHE_DIR / f"{key}.json").write_text(
            json.dumps(value, ensure_ascii=False), encoding="utf-8"
        )
    except Exception as e:  # pragma: no cover
        logger.debug("custdev cache write failed: %s", e)


def _normalize_insights(raw: dict) -> list[dict]:
    """Coerce one call's LLM output into a clean list of grounded insights.

    Defensive: drops insights without a real client quote, snaps unknown
    categories to 'other', and truncates long fields. Returns [] on any junk.
    """
    if not isinstance(raw, dict):
        return []
    items = raw.get("insights", [])
    if not isinstance(items, list):
        return []
    out: list[dict] = []
    for it in items:
        if not isinstance(it, dict):
            continue
        quote = str(it.get("quote", "")).strip()
        if len(quote) < 3:  # an insight without evidence is not an insight
            continue
        cat = str(it.get("category", "other")).strip().lower()
        if cat not in ALLOWED_CATEGORIES:
            cat = "other"
        out.append({
            "category": cat,
            "insight": str(it.get("insight", "")).strip()[:240],
            "quote": quote[:240],
            "recommendation": str(it.get("recommendation", "")).strip()[:240],
        })
    return out


async def _extract_one(client, sem, call_id: str, turns: list[dict], lens: str,
                       system: str, model: str) -> tuple[str, list[dict]]:
    transcript = _transcript_text(turns)
    key = _cache_key(lens, transcript, model or settings.LLM_PRIMARY_MODEL)
    cached = _cache_get(key)
    if cached is not None:
        return call_id, cached

    async with sem:
        resp = await client.complete_json(system=system, user_message=f"Расшифровка звонка:\n\n{transcript}", model=model)
    parsed = getattr(resp, "parsed", None)
    if not resp.success or parsed is None:
        logger.debug("CustDev extract failed for %s [%s]", call_id, resp.error_category)
        return call_id, []
    insights = _normalize_insights(parsed)
    _cache_put(key, insights)
    return call_id, insights


async def _extract_all(calls: list[dict], lens: str, model: str) -> dict[str, list[dict]]:
    from pipeline.llm.client import get_client

    client = get_client()
    if not client.available:
        return {}
    system = llm_custdev_system(lens)
    sem = asyncio.Semaphore(settings.LLM_CONCURRENCY)
    tasks = [_extract_one(client, sem, c["id"], c["turns"], lens, system, model) for c in calls]
    results: dict[str, list[dict]] = {}
    done, total = 0, len(tasks)
    for coro in asyncio.as_completed(tasks):
        cid, insights = await coro
        results[cid] = insights
        done += 1
        if done % 100 == 0 or done == total:
            logger.info("CustDev extraction: %d/%d", done, total)
            print(f"  CustDev extraction: {done}/{total}")
    return results


def run_custdev_llm(calls: list[dict], lens: str | None = None, model: str = "") -> dict[str, list[dict]]:
    """Synchronous entrypoint: extract CustDev insights per call via the LLM.

    calls:  [{"id": "c_00001", "turns": [{"role","text"}, ...]}]
    lens:   research focus (defaults to BASE_CUSTDEV_PROMPT)
    returns: {call_id: [insight, ...]} for every call (empty list when nothing found).
             {} if the LLM is unavailable or the batch crashed.
    """
    if not calls:
        return {}
    lens = (lens or BASE_CUSTDEV_PROMPT).strip()
    try:
        return asyncio.run(_extract_all(calls, lens, model))
    except Exception as e:  # pragma: no cover
        logger.error("CustDev LLM extraction crashed, falling back to deterministic: %s", e)
        return {}


# ── REDUCE: aggregate per-call insights into the page contract ──────────────
def _dedupe_quotes(quotes: list[dict]) -> list[dict]:
    seen, uniq = set(), []
    for q in quotes:
        k = re.sub(r"\s+", " ", q["quote"].lower())[:60]
        if k not in seen:
            seen.add(k)
            uniq.append(q)
    return uniq


def _empty_contract(prompt: str, mode: str, total: int, note: str) -> dict:
    return {
        "prompt": prompt, "mode": mode, "total_conversations": total,
        "categories": [], "summary": [], "note": note,
    }


def _reduce_llm_insights(llm_insights: dict[str, list[dict]], prompt: str) -> dict:
    """Fold {call_id: [insight]} into the {categories, summary} page contract.

    Counts are REAL (number of grounded quotes per category) — never model-guessed.
    """
    buckets: dict[str, list[dict]] = {k: [] for k in _CAT_ORDER}
    buckets["other"] = []
    for call_id, insights in llm_insights.items():
        for ins in insights:
            cat = ins.get("category", "other")
            if cat not in buckets:
                cat = "other"
            buckets[cat].append({"call_id": call_id, "quote": ins["quote"]})

    categories = []
    for key in [*_CAT_ORDER, "other"]:
        hits = _dedupe_quotes(buckets[key])
        if not hits:
            continue
        categories.append({
            "key": key,
            "label": _CAT_LABEL[key],
            "count": len(hits),
            "recommendation": _CAT_REC[key],
            "quotes": hits[:_MAX_QUOTES_PER_CATEGORY],
        })

    categories.sort(key=lambda x: x["count"], reverse=True)
    summary = [
        {"theme": c["label"], "count": c["count"], "recommendation": c["recommendation"]}
        for c in categories[:_SUMMARY_TOP_N]
    ]
    total = len(llm_insights)
    return {
        "prompt": prompt,
        "mode": "llm",
        "total_conversations": total,
        "categories": categories,
        "summary": summary,
        "note": ("Инсайты извлечены LLM по заданной тематике: модель по каждому звонку "
                 "достаёт смысл и дословную цитату клиента, а частоты считает пайплайн "
                 "(не модель)."),
    }


def _build_deterministic(features: list[dict], prompt: str) -> dict:
    """Keyword failsafe: cluster client utterances into the same category contract."""
    pat_compiled = {c["key"]: [re.compile(p, re.I) for p in c["patterns"]] for c in CATEGORIES}
    cat_hits: dict[str, list[dict]] = {c["key"]: [] for c in CATEGORIES}

    total_conv = 0
    for i, f in enumerate(features):
        if not f["analysis"].get("connected"):
            continue
        total_conv += 1
        call_id = f"c_{i:05d}"
        for ct in _client_turns_text(f["turns"]):
            low = ct.lower()
            for c in CATEGORIES:
                if any(rx.search(low) for rx in pat_compiled[c["key"]]):
                    cat_hits[c["key"]].append({"call_id": call_id, "quote": ct[:240]})
                    break  # one category per turn (first match wins)

    categories = []
    for c in CATEGORIES:
        hits = _dedupe_quotes(cat_hits[c["key"]])
        if not hits:
            continue
        categories.append({
            "key": c["key"], "label": c["label"], "count": len(hits),
            "recommendation": c["recommendation"], "quotes": hits[:_MAX_QUOTES_PER_CATEGORY],
        })

    categories.sort(key=lambda x: x["count"], reverse=True)
    summary = [
        {"theme": c["label"], "count": c["count"], "recommendation": c["recommendation"]}
        for c in categories[:_SUMMARY_TOP_N]
    ]
    return {
        "prompt": prompt,
        "mode": "deterministic",
        "total_conversations": total_conv,
        "categories": categories,
        "summary": summary,
        "note": ("LLM выключена — инсайты собраны по ключевым словам (прототип). "
                 "С ключом в .env инсайты извлекает LLM по заданной тематике, "
                 "опираясь на дословные слова клиента."),
    }


def build_custdev(df: pd.DataFrame, features: list[dict], prompt: str | None = None,
                  llm_insights: dict[str, list[dict]] | None = None) -> dict:
    """Build custdev.json.

    If `llm_insights` is provided (per-call results from run_custdev_llm), REDUCE
    them into the page contract (mode="llm"). Otherwise fall back to the
    deterministic keyword clustering (mode="deterministic").

    Both branches emit an identical shape, so the React page is source-agnostic.
    """
    prompt = (prompt or BASE_CUSTDEV_PROMPT)

    if llm_insights is not None:
        if llm_insights:
            return _reduce_llm_insights(llm_insights, prompt)
        # LLM ran but returned nothing usable — be honest, don't fake a deterministic pass.
        connected = sum(1 for f in features if f["analysis"].get("connected"))
        return _empty_contract(
            prompt, "llm", connected,
            "LLM не вернула инсайтов (пустой результат или сбой). Проверьте ключ и лимиты.",
        )

    return _build_deterministic(features, prompt)
