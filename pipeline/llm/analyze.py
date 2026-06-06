"""LLM dialogue analysis: prompts, output schema, and a cached batch runner.

This is the "real" analysis layer the PO asked for. The deterministic classifier
in stages.py is the FAILSAFE; this module is what runs when API keys are present.

DESIGN (as a voice + LLM engineer):
  - Every stage is CLIENT-GROUNDED: a milestone counts only when the CLIENT's
    own words confirm it. The bot proposing a meeting is NOT a meeting; the client
    saying "да, давайте завтра" is.
  - We split signals into two layers:
      * context (uncontrollable by the prompt): dozvon, line quality, ASR collapse.
      * controllable (the prompt): opener -> offer -> meeting -> qualification.
    The dashboard fixes only the controllable layer; the context layer is routed
    to the dialer/telephony/ASR owners.
  - Output is a strict JSON object (schema below) so the pipeline can merge LLM
    labels with deterministic ones and compute identical metrics either way.
  - Disk cache keyed by a hash of the transcript: a re-run over 2 000 calls is free.

The schema mirrors what stages.py produces, so metrics.py is source-agnostic.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from pathlib import Path
from typing import Optional

from pipeline.config import settings

logger = logging.getLogger(__name__)

CACHE_DIR = Path(".llm_cache")

# ── Pattern taxonomy the model may assign (curated for THIS bot) ────────────
# Keeping the id space aligned with the deterministic classifier so the UI can
# render either source identically.
PATTERN_TAXONOMY = """
Положительные паттерны бота:
  PSY-010  Запрос разрешения в опенере ("30 секунд займёт, ладно?")
  PSY-047  Альтернативное закрытие ("вам утром или вечером удобнее?")
  PSY-082  Feel-Felt-Found (нормализация возражения через опыт других)
Отрицательные паттерны бота:
  PSY-011  Питч в лоб в опенере (продаёт раньше, чем получил согласие)
  PSY-124  Затянутый монолог-питч (>60 слов в одной реплике)
  PSY-094  Игнор возражения (клиент возразил — бот не отработал и продолжил скрипт)
  PSY-095  Преждевременная сдача ("направлю материалы в мессенджер" вместо закрытия)
  PSY-106  Нет закрытия (бот не предложил конкретный следующий шаг/CTA)
  PSY-200  ASR-петля (бот повторяет один и тот же вопрос, не слыша клиента)
  PSY-201  Глухота к проблеме связи (клиент говорит "не слышу/алло" — бот продолжает питч)
"""

SYSTEM_PROMPT = f"""Ты — старший аналитик качества диалогов голосового AI-агента продаж Botamin.
Бот сам звонит по холодной базе на русском и ведёт диалог. Его миссия — провести
клиента по цепочке из 4 задач, СТРОГО по порядку:
  1. Поздороваться и получить СОГЛАСИЕ на разговор.
  2. Рассказать оффер (ИИ-продавец для отдела продаж).
  3. Договориться о встрече (созвон с экспертом ~15 минут онлайн).
  4. Квалифицировать клиента (объём базы на прозвон, кто отвечает за продажи и т.п.).

ТВОЯ ЗАДАЧА: по расшифровке одного звонка вернуть строгий JSON-анализ.

ЖЕЛЕЗНОЕ ПРАВИЛО — КЛИЕНТ-ПРИВЯЗАННОСТЬ:
Стадия засчитывается ТОЛЬКО если её подтверждают слова САМОГО КЛИЕНТА, а не бота.
  - Бот предложил встречу ≠ встреча. Встреча = клиент согласился ("да, давайте",
    назвал/принял время, "договорились", "подойдёт").
  - Бот проговорил оффер ≠ оффер донесён. Оффер донесён = клиент УСЛЫШАЛ и остался
    в диалоге/среагировал по смыслу (задал вопрос, возразил по сути, согласился слушать).
  - Согласие = клиент явно дал добро продолжать ("ладно", "слушаю", "говорите",
    "да, интересно"). Простое "да" в ответ на "слышно?" — это НЕ согласие, это связь.

ДВА СЛОЯ ПОТЕРЬ (важно для атрибуции):
  - context (НЕуправляемо промптом): не дозвонились, клиент сразу бросил трубку,
    обвал связи/ASR ("не слышу", "алло", "что?", "тихо", бот повторяется из-за
    нераспознавания). Это зона диалера/телефонии/ASR.
  - controllable (управляемо промптом): слабый опенер, занудный питч, не отработал
    возражение, не закрыл на встречу, кривая квалификация.
Поле loss_layer указывает, на каком слое звонок потерял клиента.

ТАКСОНОМИЯ ПАТТЕРНОВ (выбирай id ТОЛЬКО отсюда):
{PATTERN_TAXONOMY}

СХЕМА ОТВЕТА (верни РОВНО эти ключи):
{{
  "connected": true,
  "furthest_stage": 0,
  "stage_evidence": {{
    "consent":        {{"reached": false, "quote": ""}},
    "offer_engaged":  {{"reached": false, "quote": ""}},
    "meeting_agreed": {{"reached": false, "quote": ""}},
    "qualified":      {{"reached": false, "quote": ""}}
  }},
  "outcome": "no_contact|contact_only|refused|consent|offer_engaged|meeting|qualified",
  "disqualified": false,
  "end_attribution": "client_hangup|bot_hangup|technical|completed",
  "objections": [{{"type": "price|no_need|have_alternative|no_time|no_budget|send_info|have_internal|not_priority|gatekeeper", "quote": ""}}],
  "bot_patterns": [{{"id": "PSY-XXX", "polarity": "positive|negative", "quote": ""}}],
  "voice": {{
    "asr_breakdown": false,
    "asr_severity": "none|low|medium|high",
    "responsiveness": 0.0,
    "repair_attempts": 0,
    "bot_talk_share": 0.0,
    "longest_bot_monologue_words": 0
  }},
  "quality_score": 0.0,
  "loss_reason": "no_answer|instant_hangup|asr_breakdown|weak_opener|boring_pitch|objection_unhandled|no_close|disqualified|reached_goal|other",
  "loss_layer": "context|controllable|none",
  "summary": ""
}}

ПОЯСНЕНИЯ ПО ПОЛЯМ:
  furthest_stage: самая дальняя ПОДТВЕРЖДЁННАЯ КЛИЕНТОМ стадия:
    0=только контакт, 1=согласие, 2=оффер донесён, 3=встреча, 4=квалификация.
    Если достигнута стадия N — все меньшие тоже считаются достигнутыми.
  responsiveness: 0..1 — насколько реплики бота отвечают на ПОСЛЕДНЮЮ реплику клиента
    (1 = всегда по делу, 0 = бот игнорирует сказанное / гонит скрипт).
  bot_talk_share: доля слов бота от всех слов (0..1).
  quality_score: 0..1 — общая оценка качества ведения диалога ботом (опираясь на
    отзывчивость, отработку возражений, уместность закрытия; НЕ штрафуй за обвал связи).
  disqualified: true, если бот сам отказал клиенту (например, база меньше порога).
  quote: дословная короткая цитата-доказательство (до ~120 символов) или "".
"""


def _transcript_text(turns: list[dict]) -> str:
    """Render parsed turns as a readable transcript for the model."""
    out = []
    for t in turns:
        role = "Бот" if t["role"] == "bot" else "Клиент" if t["role"] == "client" else "?"
        out.append(f"{role}: {t['text']}")
    return "\n".join(out)


def _cache_key(transcript: str, model: str) -> str:
    h = hashlib.sha256((model + "\x00" + transcript).encode("utf-8")).hexdigest()
    return h[:24]


def _cache_get(key: str) -> Optional[dict]:
    p = CACHE_DIR / f"{key}.json"
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return None
    return None


def _cache_put(key: str, value: dict) -> None:
    CACHE_DIR.mkdir(exist_ok=True)
    try:
        (CACHE_DIR / f"{key}.json").write_text(
            json.dumps(value, ensure_ascii=False), encoding="utf-8"
        )
    except Exception as e:  # pragma: no cover
        logger.debug("cache write failed: %s", e)


def _normalize(raw: dict) -> dict:
    """Validate + coerce the model output into a stable shape.

    Defensive: models sometimes omit keys or return strings where we want numbers.
    A bad field falls back to a safe default rather than crashing the pipeline.
    """
    def num(v, default=0.0):
        try:
            return float(v)
        except (TypeError, ValueError):
            return default

    def clamp01(v):
        return max(0.0, min(1.0, num(v)))

    se = raw.get("stage_evidence", {}) or {}
    def stage_reached(name):
        node = se.get(name, {}) or {}
        return bool(node.get("reached", False)), str(node.get("quote", ""))[:200]

    consent_r, consent_q = stage_reached("consent")
    offer_r, offer_q = stage_reached("offer_engaged")
    meeting_r, meeting_q = stage_reached("meeting_agreed")
    qual_r, qual_q = stage_reached("qualified")

    # Derive furthest from evidence (trust evidence over a possibly-stray int),
    # honouring implication: higher stage implies all lower stages.
    fs = 0
    if consent_r:
        fs = 1
    if offer_r:
        fs = max(fs, 2)
    if meeting_r:
        fs = max(fs, 3)
    if qual_r:
        fs = max(fs, 4)
    # If the model gave an explicit furthest_stage and it's consistent, keep the max.
    try:
        fs = max(fs, int(raw.get("furthest_stage", 0)))
    except (TypeError, ValueError):
        pass
    fs = max(0, min(4, fs))

    voice = raw.get("voice", {}) or {}
    return {
        "source": "llm",
        "connected": bool(raw.get("connected", True)),
        "furthest_stage": fs,
        "stage_evidence": {
            "consent": {"reached": consent_r, "quote": consent_q},
            "offer_engaged": {"reached": offer_r, "quote": offer_q},
            "meeting_agreed": {"reached": meeting_r, "quote": meeting_q},
            "qualified": {"reached": qual_r, "quote": qual_q},
        },
        "outcome": str(raw.get("outcome", "contact_only")),
        "disqualified": bool(raw.get("disqualified", False)),
        "end_attribution": str(raw.get("end_attribution", "")),
        "objections": [
            {"type": str(o.get("type", "")), "quote": str(o.get("quote", ""))[:200]}
            for o in (raw.get("objections", []) or []) if isinstance(o, dict)
        ],
        "bot_patterns": [
            {"id": str(p.get("id", "")), "polarity": str(p.get("polarity", "")),
             "quote": str(p.get("quote", ""))[:200]}
            for p in (raw.get("bot_patterns", []) or []) if isinstance(p, dict)
        ],
        "voice": {
            "asr_breakdown": bool(voice.get("asr_breakdown", False)),
            "asr_severity": str(voice.get("asr_severity", "none")),
            "responsiveness": clamp01(voice.get("responsiveness", 0)),
            "repair_attempts": int(num(voice.get("repair_attempts", 0))),
            "bot_talk_share": clamp01(voice.get("bot_talk_share", 0)),
            "longest_bot_monologue_words": int(num(voice.get("longest_bot_monologue_words", 0))),
        },
        "quality_score": clamp01(raw.get("quality_score", 0)),
        "loss_reason": str(raw.get("loss_reason", "other")),
        "loss_layer": str(raw.get("loss_layer", "none")),
        "summary": str(raw.get("summary", ""))[:400],
    }


async def _analyze_one(client, sem, call_id, turns, model) -> tuple[str, Optional[dict]]:
    transcript = _transcript_text(turns)
    key = _cache_key(transcript, model or settings.LLM_PRIMARY_MODEL)
    cached = _cache_get(key)
    if cached is not None:
        return call_id, cached

    async with sem:
        resp = await client.complete_json(
            system=SYSTEM_PROMPT,
            user_message=f"Расшифровка звонка:\n\n{transcript}",
            model=model,
        )
    parsed = getattr(resp, "parsed", None)
    if not resp.success or parsed is None:
        logger.warning("LLM analyze failed for %s [%s]: %s",
                       call_id, resp.error_category, (resp.error or "")[:120])
        return call_id, None
    result = _normalize(parsed)
    _cache_put(key, result)
    return call_id, result


async def _analyze_all(calls: list[dict], model: str) -> dict[str, dict]:
    from pipeline.llm.client import get_client

    client = get_client()
    if not client.available:
        return {}
    sem = asyncio.Semaphore(settings.LLM_CONCURRENCY)
    tasks = [
        _analyze_one(client, sem, c["id"], c["turns"], model)
        for c in calls
    ]
    results: dict[str, dict] = {}
    done = 0
    total = len(tasks)
    for coro in asyncio.as_completed(tasks):
        cid, res = await coro
        if res is not None:
            results[cid] = res
        done += 1
        if done % 100 == 0 or done == total:
            logger.info("LLM analysis: %d/%d (ok=%d)", done, total, len(results))
            print(f"  LLM analysis: {done}/{total} (ok={len(results)})")
    return results


def run_analysis(calls: list[dict], model: str = "") -> dict[str, dict]:
    """Synchronous entrypoint for the pipeline.

    calls: [{"id": "c_0001", "turns": [{"role","text"}, ...]}]
    returns: {call_id: normalized_analysis_dict} — only for calls the LLM handled.
    """
    if not calls:
        return {}
    try:
        return asyncio.run(_analyze_all(calls, model))
    except Exception as e:  # pragma: no cover
        logger.error("LLM batch analysis crashed, falling back to deterministic: %s", e)
        return {}
