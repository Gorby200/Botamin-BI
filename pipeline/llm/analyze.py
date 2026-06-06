"""Batched single-pass LLM dialogue analysis.

ONE rich analysis per dialogue (stages + ~60 catalog patterns + V4 quality layers +
product-intel + recommendations), but dialogues are sent in BATCHES so the heavy
system prompt (catalog + rubric, ~2.5K tokens) is billed once per batch instead of
once per call. The deterministic classifier in stages.py is the FAILSAFE.

ROBUSTNESS (LLM-engineering defenses, cheapest first):
  1. Per-DIALOGUE disk cache (not per-batch): a changed/added dialogue never
     invalidates its neighbours; re-runs and partial successes are reused.
  2. Salvage-by-object parsing: a brace-matching scanner recovers every COMPLETE
     {...} object even if the surrounding array is truncated or fenced — a cut-off
     response still yields the analyses that did arrive.
  3. Bisect-on-failure: dialogues not returned/invalid in a batch are split in half
     and retried (with a reinforced "valid JSON only" instruction), isolating a
     single pathological transcript instead of dropping the whole batch.
  4. Deterministic failsafe: anything that never parses keeps its stages.py analysis.

Self-checks gate what gets cached: an item must be a usable analysis, and its claimed
outcome may not exceed the client-evidence-confirmed stage.

The per-item contract mirrors stages.py (+quality/+product_intel) so metrics.py and the
frontend stay source-agnostic. Python — not the model — computes every number.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
from pathlib import Path
from typing import Optional

from pipeline.config import settings
from pipeline import patterns
from pipeline import methodology

logger = logging.getLogger(__name__)

CACHE_DIR = Path(".llm_cache")

# ── Analysis guidance (shared, prompt-cache-stable) ─────────────────────────
# Kept separate from batch I/O so the cache key depends only on the ANALYSIS rules,
# not on batch packing — single-call and batched runs reuse the same cached results.
_PER_ITEM_SCHEMA = """{
  "id": "<тот же id диалога>",
  "connected": true,
  "furthest_stage": 0,
  "stage_evidence": {
    "consent":        {"reached": false, "quote": ""},
    "offer_engaged":  {"reached": false, "quote": ""},
    "meeting_agreed": {"reached": false, "quote": ""},
    "qualified":      {"reached": false, "quote": ""}
  },
  "outcome": "no_contact|contact_only|refused|consent|offer_engaged|meeting|qualified",
  "disqualified": false,
  "end_attribution": "client_hangup|bot_hangup|technical|completed",
  "objections": [{"type": "price|no_need|have_alternative|no_time|no_budget|send_info|have_internal|not_priority|gatekeeper", "quote": "", "root_cause": ""}],
  "bot_patterns": [{"id": "PSY-XXX", "quote": "дословная реплика бота-доказательство"}],
  "quality_layers": {"macro": 0.0, "micro": 0.0, "overlap": 0.0},
  "voice": {"asr_breakdown": false, "asr_severity": "none|low|medium|high", "responsiveness": 0.0, "repair_attempts": 0, "bot_talk_share": 0.0, "longest_bot_monologue_words": 0},
  "product_intel": {
    "insights": [{"category": "pain|wish|competitor|pricing|decision|trust|timing|usecase|other", "insight": "суть на языке продакта", "quote": "дословная цитата клиента", "recommendation": "что сделать"}],
    "jtbd": {"functional": "", "emotional": "", "trigger": ""}
  },
  "loss_reason": "no_answer|instant_hangup|asr_breakdown|weak_opener|boring_pitch|objection_unhandled|no_close|disqualified|reached_goal|other",
  "loss_layer": "context|controllable|none",
  "summary": "1–2 предложения",
  "recommendations": ["конкретная гипотеза для промпта/продукта"]
}"""

_ANALYSIS_GUIDE = f"""Ты — старший аналитик качества диалогов голосового AI-агента продаж Botamin.
Бот сам звонит по холодной B2B-базе на русском. Его миссия — провести клиента по 4 задачам:
  1) поздороваться и получить СОГЛАСИЕ; 2) рассказать оффер; 3) договориться о встрече
  (созвон с экспертом ~15 мин онлайн); 4) квалифицировать (объём базы, кто отвечает за продажи).

━━━ A. СТАДИИ (клиент-привязанность — железное правило) ━━━
Стадия засчитывается ТОЛЬКО если её подтверждают слова САМОГО КЛИЕНТА, не бота.
  - Бот предложил встречу ≠ встреча. Встреча = клиент согласился (назвал/принял время, «договорились»).
  - Оффер донесён = клиент УСЛЫШАЛ и среагировал по смыслу. «Да» в ответ на «слышно?» — это связь, НЕ согласие.
ДВА СЛОЯ ПОТЕРЬ: context (не дозвон/сброс/обвал связи — НЕуправляемо промптом) и
controllable (слабый опенер/питч/возражение/закрытие — управляемо промптом).

━━━ B. ПСИХОЛОГИЧЕСКИЕ ПАТТЕРНЫ БОТА ━━━
Отмечай паттерны ТОЛЬКО из этого каталога (id строго отсюда), КОНСЕРВАТИВНО (нужна явная
последовательность и доказательство в репликах БОТА; лучше пропустить, чем выдумать).
{patterns.catalog_for_prompt()}

━━━ C. {methodology.rubric_for_prompt()}

━━━ D. CUSTDEV / ПРОДУКТОВЫЕ ИНСАЙТЫ ━━━
Из слов КЛИЕНТА извлеки продуктовые сигналы (каждый — с ДОСЛОВНОЙ цитатой клиента),
категория строго: pain|wish|competitor|pricing|decision|trust|timing|usecase|other.
Ничего не выдумывай; нет сигнала — пустой список. Сформулируй JTBD, если слышно.

ПОЯСНЕНИЯ: furthest_stage — самая дальняя ПОДТВЕРЖДЁННАЯ КЛИЕНТОМ стадия (0..4); достигнута N →
все меньшие тоже. responsiveness/bot_talk_share 0..1. quality_layers — три числа 0..10
(итог/грейд посчитает система). quote — дословно, до ~120 символов, или "". Тексты — на русском."""

# ── Batch system prompt: strong output mandate + per-item schema ────────────
BATCH_SYSTEM_PROMPT = f"""{_ANALYSIS_GUIDE}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ФОРМАТ РАБОТЫ — ПАКЕТНЫЙ. Тебе дают НЕСКОЛЬКО диалогов (каждый помечен `id=...`).
Проанализируй КАЖДЫЙ независимо и верни РЕЗУЛЬТАТЫ ВСЕХ диалогов.

ЖЁСТКИЕ ТРЕБОВАНИЯ К ВЫВОДУ (нарушение = бесполезный ответ):
  1. Верни РОВНО ОДИН валидный JSON-массив `[ ... ]` — один объект на каждый входной диалог.
  2. НИКАКОГО текста, пояснений или markdown до или после массива. Только массив.
  3. В каждом объекте ПЕРВЫМ полем укажи "id" — точно тот же id, что во входе.
  4. Каждый объект — строго по схеме ниже, со ВСЕМИ ключами. Если по диалогу нечего сказать —
     всё равно верни объект с его id и значениями по умолчанию.
  5. Не обрывай массив на середине объекта; закрой все скобки.
  6. Числа — числами (не строками), булевы — true/false.

СХЕМА ОДНОГО ОБЪЕКТА:
{_PER_ITEM_SCHEMA}

ПЕРЕД ОТВЕТОМ САМОПРОВЕРКА: (а) число объектов = числу входных диалогов; (б) у каждого есть "id";
(в) JSON валиден и массив закрыт; (г) outcome не выше, чем подтверждённая клиентом стадия."""

_RETRY_REINFORCEMENT = ("\n\nВНИМАНИЕ: верни СТРОГО валидный JSON-массив объектов и НИЧЕГО больше. "
                        "Без markdown, без текста до/после. Закрой все скобки.")

# Recursion / sizing knobs.
_MAX_BISECT_DEPTH = 4
_OUTCOME_RANK = {"no_contact": -1, "contact_only": 0, "refused": 0, "consent": 1,
                 "offer_engaged": 2, "meeting": 3, "qualified": 4}
_STAGE_TO_OUTCOME = {0: "contact_only", 1: "consent", 2: "offer_engaged", 3: "meeting", 4: "qualified"}


def _transcript_text(turns: list[dict]) -> str:
    out = []
    for t in turns:
        role = "Бот" if t["role"] == "bot" else "Клиент" if t["role"] == "client" else "?"
        out.append(f"{role}: {t['text']}")
    return "\n".join(out)


# ── Per-dialogue cache (independent of batching) ────────────────────────────
_GUIDE_HASH = hashlib.sha256((_ANALYSIS_GUIDE + _PER_ITEM_SCHEMA).encode()).hexdigest()[:8]


def _cache_key(transcript: str, model: str) -> str:
    payload = f"analyze3:{model}\x00{_GUIDE_HASH}\x00{transcript}"
    return "an_" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:21]


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
        (CACHE_DIR / f"{key}.json").write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
    except Exception as e:  # pragma: no cover
        logger.debug("cache write failed: %s", e)


# ── Robust JSON parsing (repair + salvage) ──────────────────────────────────
def _strip_fences(text: str) -> str:
    t = text.strip()
    t = re.sub(r"^```(?:json)?\s*", "", t)
    t = re.sub(r"\s*```$", "", t)
    return t.strip()


def _extract_json_objects(text: str) -> list[dict]:
    """Salvage every COMPLETE top-level {...} object via brace matching.

    String-aware (ignores braces inside strings, honours escapes). Recovers analyses
    even when the enclosing array is truncated, fenced, or has junk between objects.
    """
    objs: list[dict] = []
    depth = 0
    start = -1
    in_str = False
    esc = False
    for i, ch in enumerate(text):
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            if depth > 0:
                depth -= 1
                if depth == 0 and start >= 0:
                    chunk = text[start:i + 1]
                    try:
                        obj = json.loads(chunk)
                        if isinstance(obj, dict):
                            objs.append(obj)
                    except Exception:
                        # try a light repair: drop trailing commas before } or ]
                        try:
                            repaired = re.sub(r",\s*([}\]])", r"\1", chunk)
                            obj = json.loads(repaired)
                            if isinstance(obj, dict):
                                objs.append(obj)
                        except Exception:
                            pass
                    start = -1
    return objs


def _parse_batch(text: str) -> list[dict]:
    """Best-effort: clean array first, else salvage individual objects."""
    if not text or not text.strip():
        return []
    t = _strip_fences(text)
    try:
        v = json.loads(t)
        if isinstance(v, list):
            return [o for o in v if isinstance(o, dict)]
        if isinstance(v, dict):
            for k in ("results", "items", "analyses", "dialogues"):
                if isinstance(v.get(k), list):
                    return [o for o in v[k] if isinstance(o, dict)]
            return [v]
    except Exception:
        pass
    return _extract_json_objects(t)


def _match_items(items: list[dict], chunk: list[dict]) -> dict[str, dict]:
    """Map parsed items to chunk ids. Prefer explicit `id`; positional fallback when
    the model omitted ids but returned exactly the expected count."""
    ids = [c["id"] for c in chunk]
    id_set = set(ids)
    by_id: dict[str, dict] = {}
    unkeyed: list[dict] = []
    for it in items:
        iid = str(it.get("id") or it.get("i") or "").strip()
        if iid in id_set and iid not in by_id:
            by_id[iid] = it
        else:
            unkeyed.append(it)
    if unkeyed:
        leftover_ids = [i for i in ids if i not in by_id]
        if len(unkeyed) == len(leftover_ids):  # safe positional pairing
            for cid, it in zip(leftover_ids, unkeyed):
                by_id[cid] = it
    return by_id


# ── Self-checks ─────────────────────────────────────────────────────────────
def _is_usable(obj: dict) -> bool:
    """An item is usable only if it carries real analysis signal (not just an id)."""
    if not isinstance(obj, dict):
        return False
    return bool(obj.get("stage_evidence")) or "outcome" in obj or "quality_layers" in obj


def _num(v, default=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _clamp01(v):
    return max(0.0, min(1.0, _num(v)))


def _normalize_patterns(raw_list) -> list[dict]:
    out = []
    for p in (raw_list or []):
        if not isinstance(p, dict):
            continue
        pid = str(p.get("id", "")).strip().upper()
        if pid not in patterns.ALLOWED_IDS:
            continue
        out.append({"id": pid, "polarity": patterns.pattern_meta(pid)["polarity"],
                    "quote": str(p.get("quote", ""))[:200]})
    return out


def _normalize_product_intel(raw) -> dict:
    raw = raw if isinstance(raw, dict) else {}
    insights = raw.get("insights", [])
    insights = insights if isinstance(insights, list) else []
    clean = []
    for it in insights:
        if not isinstance(it, dict):
            continue
        quote = str(it.get("quote", "")).strip()
        if len(quote) < 3:
            continue
        clean.append({
            "category": str(it.get("category", "other")).strip().lower()[:24],
            "insight": str(it.get("insight", "")).strip()[:240],
            "quote": quote[:240],
            "recommendation": str(it.get("recommendation", "")).strip()[:240],
        })
    jtbd = raw.get("jtbd", {})
    jtbd = jtbd if isinstance(jtbd, dict) else {}
    return {
        "insights": clean,
        "jtbd": {"functional": str(jtbd.get("functional", "")).strip()[:240],
                 "emotional": str(jtbd.get("emotional", "")).strip()[:240],
                 "trigger": str(jtbd.get("trigger", "")).strip()[:240]},
    }


def _normalize(raw: dict) -> dict:
    """Coerce one model item into the stable contract; Python computes quality numbers
    and reconciles outcome with the evidence-confirmed stage (a self-check)."""
    se = raw.get("stage_evidence", {}) or {}

    def stage_reached(name):
        node = se.get(name, {}) or {}
        return bool(node.get("reached", False)), str(node.get("quote", ""))[:200]

    consent_r, consent_q = stage_reached("consent")
    offer_r, offer_q = stage_reached("offer_engaged")
    meeting_r, meeting_q = stage_reached("meeting_agreed")
    qual_r, qual_q = stage_reached("qualified")

    fs = 0
    if consent_r:
        fs = 1
    if offer_r:
        fs = max(fs, 2)
    if meeting_r:
        fs = max(fs, 3)
    if qual_r:
        fs = max(fs, 4)
    try:
        fs = max(fs, int(raw.get("furthest_stage", 0)))
    except (TypeError, ValueError):
        pass
    fs = max(0, min(4, fs))

    # Self-check: outcome may not claim more advancement than evidence confirms.
    outcome = str(raw.get("outcome", "contact_only"))
    if _OUTCOME_RANK.get(outcome, 0) > fs:
        outcome = _STAGE_TO_OUTCOME.get(fs, "contact_only")

    disqualified = bool(raw.get("disqualified", False))
    voice = raw.get("voice", {}) or {}
    layers = raw.get("quality_layers", {}) or {}
    quality = methodology.quality_from_layers(
        layers.get("macro", 0), layers.get("micro", 0), layers.get("overlap", 0),
        furthest_stage=fs, disqualified=disqualified,
    )

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
        "outcome": outcome,
        "disqualified": disqualified,
        "end_attribution": str(raw.get("end_attribution", "")),
        "objections": [
            {"type": str(o.get("type", "")), "quote": str(o.get("quote", ""))[:200],
             "root_cause": str(o.get("root_cause", ""))[:200]}
            for o in (raw.get("objections", []) or []) if isinstance(o, dict)
        ],
        "bot_patterns": _normalize_patterns(raw.get("bot_patterns", [])),
        "voice": {
            "asr_breakdown": bool(voice.get("asr_breakdown", False)),
            "asr_severity": str(voice.get("asr_severity", "none")),
            "responsiveness": _clamp01(voice.get("responsiveness", 0)),
            "repair_attempts": int(_num(voice.get("repair_attempts", 0))),
            "bot_talk_share": _clamp01(voice.get("bot_talk_share", 0)),
            "longest_bot_monologue_words": int(_num(voice.get("longest_bot_monologue_words", 0))),
        },
        "quality_score": round(quality["total"] / 10.0, 4),
        "quality": quality,
        "product_intel": _normalize_product_intel(raw.get("product_intel", {})),
        "loss_reason": str(raw.get("loss_reason", "other")),
        "loss_layer": str(raw.get("loss_layer", "none")),
        "summary": str(raw.get("summary", ""))[:400],
        "recommendations": [str(r).strip()[:240] for r in (raw.get("recommendations", []) or [])
                            if isinstance(r, str) and r.strip()][:6],
    }


# ── Batch packing + sizing ──────────────────────────────────────────────────
def _pack_batch(chunk: list[dict]) -> str:
    blocks = [f"=== ДИАЛОГ id={c['id']} ===\n{_transcript_text(c['turns'])}" for c in chunk]
    return (f"Проанализируй каждый из {len(chunk)} диалогов ниже и верни JSON-массив "
            f"из {len(chunk)} объектов (по одному на диалог, с тем же id).\n\n"
            + "\n\n".join(blocks))


def _output_budget(n: int) -> int:
    """Scale output tokens with batch size, capped by config (Anthropic fallback ≤8192)."""
    return min(settings.LLM_ANALYZE_MAX_TOKENS, 700 + n * 1200)


# ── Batch runner with bisect-on-failure ─────────────────────────────────────
async def _analyze_chunk(client, sem, chunk: list[dict], model: str, depth: int) -> dict[str, dict]:
    """Analyze a chunk in ONE request; bisect/retry the dialogues that don't come back."""
    if not chunk:
        return {}
    system = BATCH_SYSTEM_PROMPT + (_RETRY_REINFORCEMENT if depth > 0 else "")
    async with sem:
        resp = await client.complete(
            system=system,
            user_message=_pack_batch(chunk),
            model=model,
            max_tokens=_output_budget(len(chunk)),
        )

    results: dict[str, dict] = {}
    if resp.success:
        matched = _match_items(_parse_batch(resp.content), chunk)
        for cid, obj in matched.items():
            if _is_usable(obj):
                results[cid] = _normalize(obj)
    elif resp.error_category == "auth":
        logger.error("LLM auth error — aborting batch analysis: %s", (resp.error or "")[:120])
        return results  # no point retrying auth failures

    leftover = [c for c in chunk if c["id"] not in results]
    if leftover and depth < _MAX_BISECT_DEPTH and len(leftover) < len(chunk) + 1:
        if len(leftover) == 1:
            # retry the single straggler (deeper) with reinforcement
            if depth + 1 < _MAX_BISECT_DEPTH:
                results.update(await _analyze_chunk(client, sem, leftover, model, depth + 1))
        else:
            mid = len(leftover) // 2
            halves = await asyncio.gather(
                _analyze_chunk(client, sem, leftover[:mid], model, depth + 1),
                _analyze_chunk(client, sem, leftover[mid:], model, depth + 1),
            )
            for h in halves:
                results.update(h)
    return results


async def _analyze_all(calls: list[dict], model: str) -> dict[str, dict]:
    from pipeline.llm.client import get_client

    client = get_client()
    if not client.available:
        return {}

    mdl = model or settings.LLM_PRIMARY_MODEL
    # 1) per-dialogue cache: only un-cached dialogues hit the model.
    results: dict[str, dict] = {}
    todo: list[dict] = []
    transcripts: dict[str, str] = {}
    for c in calls:
        tx = _transcript_text(c["turns"])
        transcripts[c["id"]] = tx
        cached = _cache_get(_cache_key(tx, mdl))
        if cached is not None:
            results[c["id"]] = cached
        else:
            todo.append(c)

    if not todo:
        return results
    logger.info("LLM analysis: %d cached, %d to analyze in batches of %d",
                len(results), len(todo), settings.LLM_ANALYZE_BATCH_SIZE)

    # 2) batch the rest; batches run concurrently under the semaphore.
    bsize = max(1, settings.LLM_ANALYZE_BATCH_SIZE)
    chunks = [todo[i:i + bsize] for i in range(0, len(todo), bsize)]
    sem = asyncio.Semaphore(settings.LLM_CONCURRENCY)
    done = 0
    fresh: dict[str, dict] = {}
    for coro in asyncio.as_completed([_analyze_chunk(client, sem, ch, model, 0) for ch in chunks]):
        part = await coro
        fresh.update(part)
        done += 1
        if done % 10 == 0 or done == len(chunks):
            analyzed = len(fresh)
            logger.info("LLM analysis: batch %d/%d (analyzed=%d)", done, len(chunks), analyzed)
            print(f"  LLM analysis: batch {done}/{len(chunks)} (analyzed={analyzed}/{len(todo)})")

    # 3) cache fresh results per dialogue and merge.
    for cid, res in fresh.items():
        if cid in transcripts:
            _cache_put(_cache_key(transcripts[cid], mdl), res)
    results.update(fresh)
    return results


def run_analysis(calls: list[dict], model: str = "") -> dict[str, dict]:
    """Synchronous entrypoint.

    calls: [{"id": "c_0001", "turns": [{"role","text"}, ...]}]
    returns: {call_id: normalized_analysis_dict} — only for dialogues the LLM handled.
    Dialogues never recovered are simply absent → the caller keeps their deterministic
    analysis (failsafe).
    """
    if not calls:
        return {}
    try:
        return asyncio.run(_analyze_all(calls, model))
    except Exception as e:  # pragma: no cover
        logger.error("LLM batch analysis crashed, falling back to deterministic: %s", e)
        return {}
