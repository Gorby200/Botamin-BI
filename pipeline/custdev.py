"""CustDev insight extraction from call transcripts (prototype).

The PO wants a "voice of the customer" page: what valuable things did we hear in
the calls? This is a lightweight prototype of continuous CustDev:

  - A BASE PROMPT (editable on the page) frames WHAT we're looking for.
  - The LLM path (when a key is configured) reads transcripts through that lens and
    returns themed insights with quotes and recommendations.
  - The DETERMINISTIC failsafe clusters client utterances into insight categories by
    keyword, so the page works even with no LLM.

Output (custdev.json) feeds a page that also lets the analyst live-filter quotes by
their own topic keywords.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
from collections import Counter
from pathlib import Path

import pandas as pd

from pipeline.config import settings

logger = logging.getLogger(__name__)
CACHE_DIR = Path(".llm_cache")


# The base CustDev lens. Editable on the page; passed to the LLM verbatim.
BASE_CUSTDEV_PROMPT = (
    "Мы ищем в разговорах с клиентами всё, что помогает улучшить продукт и продажи: "
    "боли и проблемы клиента, его задачи и сценарии, пожелания и недостающие функции, "
    "возражения и их настоящие причины, чувствительность к цене, кто и как принимает "
    "решение, какими конкурентами/альтернативами пользуются, уровень доверия к ИИ-боту. "
    "Цель — понять, что важного клиенты говорят, и превратить это в гипотезы для продукта и промпта."
)

# Deterministic insight categories — client-side signals.
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


def _client_turns_text(turns: list[dict]) -> list[str]:
    return [t["text"] for t in turns if t.get("role") == "client"]


def build_custdev(df: pd.DataFrame, features: list[dict], prompt: str | None = None,
                  mode: str = "deterministic", research_results: dict | None = None) -> dict:
    """Cluster client utterances into CustDev insight categories (deterministic).

    `features[i]["turns"]` holds parsed turns; df row i aligns by position.
    Returns a structure for custdev.json.

    If research_results provided (from Tier 3 LLM analysis), merges LLM insights
    with deterministic keyword matching for comprehensive customer insights.
    """
    prompt = prompt or BASE_CUSTDEV_PROMPT

    # If Tier 3 research results available, use LLM insights directly
    if research_results and research_results.get("custdev"):
        llm_custdev = research_results["custdev"]
        return {
            "prompt": prompt,
            "mode": "llm_research",
            "total_conversations": llm_custdev.get("total_calls_analyzed", len(df)),
            "categories": llm_custdev.get("insights", {}).get("categories", []),
            "summary": llm_custdev.get("insights", {}).get("summary", []),
            "llm_insights": llm_custdev.get("insights", {}),
            "note": "Insights extracted by LLM Tier 3 research analysis with customer development lens.",
        }
    cat_hits: dict[str, list[dict]] = {c["key"]: [] for c in CATEGORIES}
    pat_compiled = {c["key"]: [re.compile(p, re.I) for p in c["patterns"]] for c in CATEGORIES}

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
                    if len(cat_hits[c["key"]]) < 60:
                        cat_hits[c["key"]].append({"call_id": call_id, "quote": ct[:240]})
                    break  # one category per turn (first match wins)

    categories = []
    for c in CATEGORIES:
        hits = cat_hits[c["key"]]
        # dedupe near-identical quotes
        seen, uniq = set(), []
        for h in hits:
            k = re.sub(r"\s+", " ", h["quote"].lower())[:60]
            if k not in seen:
                seen.add(k)
                uniq.append(h)
        categories.append({
            "key": c["key"], "label": c["label"], "count": len(hits),
            "recommendation": c["recommendation"], "quotes": uniq[:25],
        })

    categories.sort(key=lambda x: x["count"], reverse=True)
    top = [c for c in categories if c["count"] > 0][:4]
    summary = [
        {"theme": c["label"], "count": c["count"], "recommendation": c["recommendation"]}
        for c in top
    ]

    return {
        "prompt": prompt,
        "mode": mode,
        "total_conversations": total_conv,
        "categories": categories,
        "summary": summary,
        "note": ("LLM выключена — инсайты собраны по ключевым словам (прототип). "
                 "С ключом в .env инсайты извлекает LLM по заданной тематике."
                 if mode == "deterministic" else
                 "Инсайты извлечены LLM по заданной тематике."),
    }


# ── LLM CustDev system prompt (used when a key is configured) ───────────────
def llm_custdev_system(user_lens: str) -> str:
    return (
        "Ты — продуктовый исследователь (CustDev). Тебе дают расшифровки звонков "
        "голосового бота продаж. Твоя задача — извлечь ценные инсайты глазами продакта.\n\n"
        f"ФОКУС ИССЛЕДОВАНИЯ (что искать):\n{user_lens}\n\n"
        "Верни строгий JSON со списком инсайтов из ЭТОГО звонка:\n"
        '{ "insights": [ { "category": "pain|wish|competitor|pricing|decision|trust|timing|usecase|other",'
        ' "insight": "краткая суть на языке продакта", "quote": "дословная цитата клиента",'
        ' "recommendation": "что с этим сделать (продукт/промпт)" } ] }\n'
        "Если ничего ценного нет — верни {\"insights\": []}. Не выдумывай — опирайся только на слова клиента."
    )
