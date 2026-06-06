"""Deterministic, CLIENT-GROUNDED dialogue classifier (the FAILSAFE engine).

This replaces the old classifier, which had a fatal validity bug: it detected
stages from a MIX of bot and client text. The bot proposes a meeting in nearly
every call ("созвонимся с экспертом на 15 минут"), so the old code scored that
proposal as a *meeting agreement* — measuring what the bot ATTEMPTED, not what the
client AGREED to. Result: S2->S3 = 85.7% (absurd) and a useless funnel.

THE RULE (unchanged from the LLM prompt, so both engines agree):
  A stage counts ONLY when the CLIENT's own words confirm it.

OUTPUT CONTRACT:
  classify_dialogue() returns the SAME dict shape as pipeline.llm.analyze._normalize,
  with source="deterministic". metrics.py consumes either interchangeably.

TWO LAYERS:
  context (uncontrollable by prompt): no dozvon, instant hangup, ASR/line collapse.
  controllable (the prompt): opener -> offer -> meeting -> qualification.
"""
from __future__ import annotations

import re

from pipeline import methodology

# ---------------------------------------------------------------------------
# Turn parsing — data uses "bot:" / "user:" line prefixes (also tolerant of RU)
# ---------------------------------------------------------------------------
_ROLE_SPLIT = re.compile(
    r"(?m)^\s*(Пользователь|Клиент|User|Юзер|Человек|Human|Бот|Bot|Агент|Agent|Ассистент|Assistant|Система|System)\s*[:：]\s*",
    flags=re.IGNORECASE,
)
_BOT_ROLES = {"бот", "bot", "агент", "agent", "ассистент", "assistant", "система", "system"}


def _parse_turns(dialogue: str | None) -> list[dict]:
    """Parse "role: text" dialogue into [{"role": "bot"|"client", "text": ...}]."""
    if not dialogue or not dialogue.strip():
        return []
    parts = _ROLE_SPLIT.split(dialogue)
    turns: list[dict] = []
    i = 1
    while i < len(parts) - 1:
        role_raw = parts[i].strip().lower()
        text = (parts[i + 1] or "").strip()
        role = "bot" if role_raw in _BOT_ROLES else "client"
        if text:
            turns.append({"role": role, "text": text})
        i += 2
    return turns


# ---------------------------------------------------------------------------
# Lexicons — kept tight to reduce false positives (the LLM handles nuance)
# ---------------------------------------------------------------------------

# Technical statuses that mean "no real conversation"
TECH_STATUSES = {
    "не дозвонился", "не дозвон", "no answer", "no_answer", "busy", "недозвон",
    "ошибка", "error", "техническая ошибка", "сброс", "отмена", "cancelled",
    "failed", "unavailable", "недоступен", "недоступн", "абонент недоступен",
    "не взял трубку",
}

# S1 consent — client explicitly agrees to listen. Deliberately EXCLUDES bare
# "да"/"угу" (those are usually answers to "слышно?", i.e. connectivity, not consent).
CONSENT_POSITIVE = [
    r"слушаю", r"говорите", r"рассказывайте", r"расскажите", r"расскаж",
    r"\bладно\b", r"\bконечно\b", r"\bинтересно\b", r"подробнее",
    r"давайте\s*(послушаю|рассказ|услыш|по\s*быстр|кратко|говорите)",
    r"в\s+чём\s+суть", r"что\s+у\s+вас", r"по\s+какому\s+(вопросу|поводу)",
    r"\bваляй\b", r"ну\s+давай", r"да[,!\s]+интересно", r"да[,!\s]+слушаю",
    r"да[,!\s]+говорите", r"что\s+за\s+(сервис|продукт|предложен)",
]

CONSENT_NEGATIVE = [
    r"не\s+интерес", r"не\s+нужн", r"не\s+звон", r"отстан", r"не\s+надо",
    r"я\s+не\s+просил", r"уберите\s+номер", r"прекратите", r"\bхватит\b",
    r"не\s+хочу", r"спасибо,?\s+не", r"до\s+свидан", r"кладу\s+трубку",
]

# S2 offer engagement — CLIENT engages with the offer (asks, reacts on-topic)
OFFER_ENGAGE_CLIENT = [
    r"сколько\s+(стоит|это|будет)", r"как\s+это\s+работа", r"а\s+как\b",
    r"что\s+за\b", r"какой\b", r"почему\b", r"в\s+чём\b", r"а\s+что\b",
    r"расскажите\s+подроб", r"пример", r"кейс", r"а\s+вы\b", r"чем\s+(вы|это)",
]

# S3 meeting — client ACCEPTS a bot-proposed meeting
MEETING_PROPOSE_BOT = [
    r"встреч", r"созвон", r"эксперт", r"подключ", r"\bонлайн\b", r"\bдемо\b",
    r"пятнадцать\s+минут", r"15\s+минут", r"видеосвяз", r"видео-встреч",
]
MEETING_ACCEPT_CLIENT = [
    r"подойдёт", r"подойдет", r"подходит", r"удобно", r"договорил", r"согласен",
    r"\bхорошо,?\s+давай", r"\bок,?\s+давай", r"\bдавайте\s+(в|после|завтра|созвон|на)\b",
    r"\bв\s+\d{1,2}([:\.]\d{2})?\b", r"\bв\s+\d{1,2}\s+час", r"можно\s+(в|на)\b",
    r"(завтра|послезавтра|в\s+понедельник|во\s+вторник|в\s+среду|в\s+четверг|в\s+пятницу)",
    r"\bдавайте\b.*\b(встреч|созвон|время|час)",
]
MEETING_REFUSE_CLIENT = [
    r"не\s+смогу", r"не\s+получится", r"не\s+надо\s+встреч", r"никак", r"не\s+буду",
    r"не\s+интересн.*встреч", r"без\s+встреч",
]

# S4 qualification — client ANSWERS a qualifying question with a concrete fact
QUAL_ANSWER_CLIENT = [
    r"\d+\s*(тысяч|тыс|человек|сотрудник|работник|контакт|менеджер|оператор|клиент)",
    r"я\s+отвеча", r"коммерческ", r"директор", r"я\s+(сам|сама)\b",
    r"(москв|питер|санкт|новосибирск|екатеринбург|казан|хабаровск|край|область|регион)",
    r"(b2b|b2c|оптов|рознич|производ|строит|металл|логист|грузоперевоз|недвиж)",
    r"база\s+(в\s+месяц|компан|контакт)", r"в\s+месяц\s+\d+",
]

# Repair / ASR-friction markers (CLIENT side) — context layer
REPAIR_MARKERS = [
    r"повтор", r"не\s+(расслыш|понял|поняла|понятно|понимаю)", r"\bчто\?",
    r"что\s+вы\s+сказал", r"простите\?", r"можно\s+ещё\s+раз", r"ещё\s+раз",
    r"еще\s+раз", r"непонятн", r"не\s+слыш", r"вас\s+не\s+слышно", r"плохо\s+слышно",
    r"\bалло\b", r"\bаллё\b", r"\bтихо\b", r"связь", r"вы\s+здесь",
]

# Premature surrender / brush-off (bot disqualifies or punts to "send materials")
SURRENDER_BOT = [
    r"направлю\s+материал", r"пришлю\s+(на\s+почту|материал|в\s+мессендж)",
    r"скину\s+(на\s+почт|материал|в\s+мессендж)", r"отправлю\s+(на\s+почт|материал)",
    r"вернёмся\s+к\s+идее", r"когда\s+объёмы\s+вырастут", r"посмотрите\s+в\s+удобное",
]

OBJECTION_KEYWORDS: dict[str, list[str]] = {
    "price": [r"дорого", r"стоимост", r"\bцен[аыу]\b", r"бюджет\s+не", r"сколько\s+стоит"],
    "no_need": [r"не\s+нужн", r"не\s+актуальн", r"не\s+интерес", r"не\s+требу", r"у\s+нас\s+всё\s+есть"],
    "have_alternative": [r"уже\s+есть", r"уже\s+пользу", r"уже\s+работ", r"другой\s+сервис", r"конкурент"],
    "no_time": [r"нет\s+времени", r"не\s+сейчас", r"\bпозже\b", r"\bзанят", r"перезвон", r"некогда", r"спешу"],
    "no_budget": [r"нет\s+бюджета", r"бюджет\s+закон", r"денег\s+нет", r"нет\s+денег", r"средств\s+нет"],
    "send_info": [r"пришлит", r"скиньт", r"отправьт", r"на\s+почт", r"в\s+телегра", r"в\s+ватсап", r"презентац"],
    "have_internal": [r"свои\s+разработ", r"свой\s+отдел", r"сами\s+дел", r"внутренн", r"сами\s+справл"],
    "not_priority": [r"не\s+приоритет", r"не\s+в\s+приорит", r"не\s+рассматрив"],
    "gatekeeper": [r"не\s+я\s+решаю", r"это\s+к\s+(директор|руководств|коммерческ)", r"передам\b", r"я\s+секретар"],
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _any(patterns: list[str], text: str) -> bool:
    return any(re.search(p, text) for p in patterns)


def _first_quote(turns: list[dict], role: str, patterns: list[str]) -> str:
    for t in turns:
        if t["role"] == role and _any(patterns, t["text"].lower()):
            return t["text"][:160]
    return ""


def _is_substantive(text: str) -> bool:
    """A client turn that carries meaning (not pure ASR noise / one word)."""
    words = text.split()
    if len(words) < 2:
        return False
    noise = re.fullmatch(r"(что|алло|аллё|да|нет|ага|угу|а|э|м|ну)[\?\.\!\s]*", text.strip().lower())
    return noise is None


# ---------------------------------------------------------------------------
# Main classifier
# ---------------------------------------------------------------------------
def classify_dialogue(
    dialogue: str | None,
    status: str | None,
    end_reason: str | None,
    duration_sec: float | None,
) -> dict:
    """Classify one call into the unified analysis contract (deterministic)."""
    turns = _parse_turns(dialogue)
    bot_turns = [t for t in turns if t["role"] == "bot"]
    client_turns = [t for t in turns if t["role"] == "client"]
    client_text = " ".join(t["text"].lower() for t in client_turns)
    bot_text = " ".join(t["text"].lower() for t in bot_turns)

    # ── Connectivity (context layer) ────────────────────────────────────────
    # Three escalating gates — a sales director's view of a cold dial:
    #   responded     — a human made ANY sound (incl. reflexive "алло?/что?/нет").
    #   conversation  — a human said something SUBSTANTIVE (>=1 meaningful turn).
    # ~70% of "responders" only make reflexive noise and bounce — that is NOT a
    # conversation and must NOT inflate the funnel. The funnel base (S0) is the
    # real CONVERSATION, not "picked up and made a sound".
    status_l = (status or "").strip().lower()
    tech_fail = any(ts in status_l for ts in TECH_STATUSES)
    has_dialogue = bool(turns)
    responded = len(client_turns) >= 1
    substantive_client = sum(1 for t in client_turns if _is_substantive(t["text"]))
    connected = has_dialogue and not tech_fail and substantive_client >= 1

    # Voice / context signals
    repair_attempts = sum(1 for t in client_turns if _any(REPAIR_MARKERS, t["text"].lower()))
    asr_breakdown = repair_attempts >= 1
    asr_severity = (
        "high" if repair_attempts >= 3 else
        "medium" if repair_attempts == 2 else
        "low" if repair_attempts == 1 else "none"
    )
    bot_words = sum(len(t["text"].split()) for t in bot_turns)
    client_words = sum(len(t["text"].split()) for t in client_turns)
    total_words = bot_words + client_words
    bot_talk_share = round(bot_words / total_words, 3) if total_words else 0.0
    longest_bot_monologue = max((len(t["text"].split()) for t in bot_turns), default=0)

    # Responsiveness proxy: penalise the bot REPEATING itself (ASR-loop symptom).
    # 1.0 = no repeats; lower = bot stuck re-asking because it didn't hear the client.
    norm = lambda s: re.sub(r"\s+", " ", s.lower()).strip()[:80]
    seen, repeats = set(), 0
    for t in bot_turns:
        n = norm(t["text"])
        if n in seen:
            repeats += 1
        seen.add(n)
    responsiveness = round(1.0 - repeats / max(len(bot_turns), 1), 3)

    # ── No real conversation short-circuit ──────────────────────────────────
    if not connected:
        if not has_dialogue:
            loss_reason = "no_answer"            # never picked up / no opener
        elif not responded:
            loss_reason = "instant_hangup"       # opener delivered, client silent
        elif asr_severity in ("medium", "high"):
            loss_reason = "asr_breakdown"        # only said "не слышу/алло" — line issue
        else:
            loss_reason = "instant_brushoff"     # reflexive "что?/нет" then bounced
        return _result(
            source="deterministic", connected=False, furthest_stage=-1,
            consent=(False, ""), offer=(False, ""), meeting=(False, ""), qual=(False, ""),
            outcome="no_contact", disqualified=False,
            end_attribution=_attr(end_reason), objections=[], bot_patterns=[],
            asr_breakdown=asr_breakdown, asr_severity=asr_severity,
            responsiveness=responsiveness, repair_attempts=repair_attempts,
            bot_talk_share=bot_talk_share, longest_bot_monologue=longest_bot_monologue,
            quality_score=0.0, loss_reason=loss_reason, loss_layer="context",
            summary="Реального разговора не состоялось (контакт без содержательной реплики).",
        )

    # ── Client-grounded stage detection ─────────────────────────────────────
    refused = _any(CONSENT_NEGATIVE, client_text)
    explicit_consent = _any(CONSENT_POSITIVE, client_text)

    # S1 consent (the cold→warm gate): client signals willingness to engage.
    # S0 already requires >=1 substantive turn, so S1 needs MORE: an explicit
    # "ладно/слушаю", OR an on-topic question, OR a real back-and-forth (>=2
    # substantive turns). A single neutral substantive line stays at S0.
    asked_on_topic = _any(OFFER_ENGAGE_CLIENT, client_text)
    consent_reached = (not refused) and (explicit_consent or asked_on_topic or substantive_client >= 2)
    consent_quote = (_first_quote(turns, "client", CONSENT_POSITIVE)
                     or _first_quote(turns, "client", OFFER_ENGAGE_CLIENT)
                     or next((t["text"][:160] for t in client_turns if _is_substantive(t["text"])), ""))

    offer_in_bot = _any([r"ии-продав", r"квалифициру", r"прозванива", r"передаёт.*горяч",
                         r"запускаем", r"автоматиз", r"наш\s+(сервис|продукт)"], bot_text)
    # S2 needs MORE than S1: the client engaged with the offer specifically (asked
    # about it / objected on-topic) OR carried >=2 substantive turns into the pitch.
    offer_engage = _any(OFFER_ENGAGE_CLIENT, client_text) or substantive_client >= 2
    offer_reached = consent_reached and offer_in_bot and offer_engage
    offer_quote = _first_quote(turns, "client", OFFER_ENGAGE_CLIENT)

    bot_proposes_meeting = _any(MEETING_PROPOSE_BOT, bot_text)
    client_accepts = _any(MEETING_ACCEPT_CLIENT, client_text)
    client_refuses_meeting = _any(MEETING_REFUSE_CLIENT, client_text)
    # Accept only if there is acceptance language AND it isn't purely a refusal turn.
    meeting_reached = (
        consent_reached and bot_proposes_meeting and client_accepts
        and not (client_refuses_meeting and not client_accepts)
    )
    meeting_quote = _first_quote(turns, "client", MEETING_ACCEPT_CLIENT)

    qual_answer = _any(QUAL_ANSWER_CLIENT, client_text)
    qualified_reached = meeting_reached and qual_answer
    qual_quote = _first_quote(turns, "client", QUAL_ANSWER_CLIENT)

    # Furthest stage with implication (higher implies lower)
    furthest = 0
    if consent_reached:
        furthest = 1
    if offer_reached:
        furthest = max(furthest, 2)
    if meeting_reached:
        furthest = max(furthest, 3)
    if qualified_reached:
        furthest = max(furthest, 4)

    # Disqualification: bot punts/surrenders after engaging
    disqualified = _any(SURRENDER_BOT, bot_text)

    # ── Objections ──────────────────────────────────────────────────────────
    objections = []
    for otype, pats in OBJECTION_KEYWORDS.items():
        q = _first_quote(turns, "client", pats)
        if q:
            objections.append({"type": otype, "quote": q[:200]})

    # ── Bot patterns ─────────────────────────────────────────────────────────
    bot_patterns = _detect_patterns(
        turns, bot_turns, client_turns, longest_bot_monologue,
        disqualified, repair_attempts, repeats,
    )

    # ── Outcome ──────────────────────────────────────────────────────────────
    if qualified_reached:
        outcome = "qualified"
    elif meeting_reached:
        outcome = "meeting"
    elif offer_reached:
        outcome = "offer_engaged"
    elif consent_reached:
        outcome = "consent"
    elif refused:
        outcome = "refused"
    else:
        outcome = "contact_only"

    # ── Loss attribution (which layer lost the client) ──────────────────────
    # Honest, non-accusatory reasons. ASR/connectivity is context; everything else
    # on an engaged call is controllable by the prompt.
    if furthest >= 4:
        loss_reason, loss_layer = "reached_goal", "none"
    elif asr_severity in ("medium", "high") and furthest < 3:
        loss_reason, loss_layer = "asr_breakdown", "context"
    elif refused:
        loss_reason, loss_layer = "refused", "controllable"
    elif disqualified:
        loss_reason, loss_layer = "disqualified", "controllable"
    elif objections and furthest <= 2:
        loss_reason, loss_layer = "objection_unhandled", "controllable"
    elif furthest == 3:
        loss_reason, loss_layer = "no_qualification", "controllable"
    elif furthest == 2:
        loss_reason, loss_layer = "no_close", "controllable"
    elif furthest == 1:
        loss_reason, loss_layer = "pitch_no_traction", "controllable"
    else:  # furthest == 0: engaged but never consented
        loss_reason, loss_layer = "opener_no_consent", "controllable"

    # ── Quality score (deterministic composite proxy, 0..1) ─────────────────
    # Rewards advancement + responsiveness; not penalised for ASR (context).
    quality_score = round(
        min(1.0, 0.15 * furthest + 0.35 * responsiveness
            + (0.1 if offer_engage else 0) + (0.0 if disqualified else 0.0)),
        3,
    )

    return _result(
        source="deterministic", connected=True, furthest_stage=furthest,
        consent=(consent_reached, consent_quote),
        offer=(offer_reached, offer_quote),
        meeting=(meeting_reached, meeting_quote),
        qual=(qualified_reached, qual_quote),
        outcome=outcome, disqualified=disqualified,
        end_attribution=_attr(end_reason), objections=objections, bot_patterns=bot_patterns,
        asr_breakdown=asr_breakdown, asr_severity=asr_severity,
        responsiveness=responsiveness, repair_attempts=repair_attempts,
        bot_talk_share=bot_talk_share, longest_bot_monologue=longest_bot_monologue,
        quality_score=quality_score, loss_reason=loss_reason, loss_layer=loss_layer,
        summary=_summary(outcome, furthest, asr_severity, disqualified),
    )


def _attr(end_reason: str | None) -> str:
    er = (end_reason or "").lower()
    if "client" in er or "клиент" in er:
        return "client_hangup"
    if "bot" in er or "бот" in er:
        return "bot_hangup"
    if not er:
        return ""
    return "technical"


def _summary(outcome: str, furthest: int, asr: str, disq: bool) -> str:
    label = {
        "qualified": "Полная квалификация",
        "meeting": "Назначена встреча",
        "offer_engaged": "Оффер донесён",
        "consent": "Получено согласие",
        "refused": "Клиент отказался",
        "contact_only": "Только контакт",
        "no_contact": "Нет контакта",
    }.get(outcome, outcome)
    extra = []
    if asr in ("medium", "high"):
        extra.append("обвал связи/ASR")
    if disq:
        extra.append("бот дисквалифицировал лида")
    return label + (" · " + ", ".join(extra) if extra else "")


def _detect_patterns(turns, bot_turns, client_turns, longest_mono, disqualified,
                     repair_attempts, bot_repeats) -> list[dict]:
    pats = []

    def add(pid, polarity, quote=""):
        pats.append({"id": pid, "polarity": polarity, "quote": quote[:160]})

    # PSY-124 long monologue
    if longest_mono >= 60:
        q = next((t["text"] for t in bot_turns if len(t["text"].split()) >= 60), "")
        add("PSY-124", "negative", q)

    # PSY-011 pitch in opener
    for t in bot_turns[:1]:
        tl = t["text"].lower()
        if sum(1 for w in ("ии-продав", "запускаем", "автоматиз", "наш сервис", "наш продукт") if w in tl) >= 1 \
           and "ладно" not in tl and "?" not in t["text"]:
            add("PSY-011", "negative", t["text"])
            break

    # PSY-010 permission ask in opener (positive)
    for t in bot_turns[:2]:
        if re.search(r"(тридцать секунд|30 секунд|ладно\?|удобно говорить|не возражаете|можете уделить)", t["text"].lower()):
            add("PSY-010", "positive", t["text"])
            break

    # PSY-047 alternative close (positive)
    if _any([r"утром\s+или\s+вечер", r"в\s+какой\s+день", r"какое\s+время\s+(удобн|вам)",
             r"сегодня\s+или\s+завтра", r"в\s+первой\s+или\s+во\s+второй"],
            " ".join(t["text"].lower() for t in bot_turns)):
        add("PSY-047", "positive")

    # PSY-095 premature surrender / disqualify
    if disqualified:
        q = _first_quote(turns, "bot", SURRENDER_BOT)
        add("PSY-095", "negative", q)

    # PSY-106 no closing (bot never proposed a concrete next step)
    if not _any(MEETING_PROPOSE_BOT, " ".join(t["text"].lower() for t in bot_turns)):
        add("PSY-106", "negative")

    # PSY-094 objection ignored (client objects, next bot turn doesn't acknowledge)
    obj_signals = [r"не\s+интерес", r"не\s+нужн", r"дорого", r"нет\s+времени", r"не\s+актуальн", r"уже\s+есть"]
    ack = ["понимаю", "согласен", "действительн", "да, но", "при этом", "однако", "тем не менее", "логично"]
    for i, t in enumerate(turns):
        if t["role"] == "client" and _any(obj_signals, t["text"].lower()):
            if i + 1 < len(turns) and turns[i + 1]["role"] == "bot":
                if not any(a in turns[i + 1]["text"].lower() for a in ack):
                    add("PSY-094", "negative", t["text"])
                    break

    # PSY-200 ASR-loop (bot repeats itself)
    if bot_repeats >= 1 and repair_attempts >= 1:
        add("PSY-200", "negative")

    # PSY-201 deaf-to-connectivity (client says "не слышу/алло" and bot keeps pitching)
    for i, t in enumerate(turns):
        if t["role"] == "client" and re.search(r"не\s+слыш|вас\s+не\s+слышно|\bалло\b|\bтихо\b", t["text"].lower()):
            if i + 1 < len(turns) and turns[i + 1]["role"] == "bot":
                nb = turns[i + 1]["text"].lower()
                if any(w in nb for w in ("ии-продав", "оффер", "эксперт", "автоматиз", "квалифициру")):
                    add("PSY-201", "negative", t["text"])
                    break

    return pats


def _result(*, source, connected, furthest_stage, consent, offer, meeting, qual,
            outcome, disqualified, end_attribution, objections, bot_patterns,
            asr_breakdown, asr_severity, responsiveness, repair_attempts,
            bot_talk_share, longest_bot_monologue, quality_score, loss_reason,
            loss_layer, summary) -> dict:
    """Assemble the unified analysis contract shared with the LLM engine."""
    return {
        "source": source,
        "connected": connected,
        "furthest_stage": furthest_stage,
        "stage_evidence": {
            "consent": {"reached": consent[0], "quote": consent[1]},
            "offer_engaged": {"reached": offer[0], "quote": offer[1]},
            "meeting_agreed": {"reached": meeting[0], "quote": meeting[1]},
            "qualified": {"reached": qual[0], "quote": qual[1]},
        },
        "outcome": outcome,
        "disqualified": disqualified,
        "end_attribution": end_attribution,
        "objections": objections,
        "bot_patterns": bot_patterns,
        "voice": {
            "asr_breakdown": asr_breakdown,
            "asr_severity": asr_severity,
            "responsiveness": responsiveness,
            "repair_attempts": repair_attempts,
            "bot_talk_share": bot_talk_share,
            "longest_bot_monologue_words": longest_bot_monologue,
        },
        "quality_score": quality_score,
        # Uniform contract with the LLM engine. The deterministic failsafe has no
        # layer judgement, so we approximate all three V4 layers by quality_score
        # (methodology recomputes total/grade and adds the deterministic outcome+gap).
        "quality": methodology.quality_from_layers(
            quality_score * 10, quality_score * 10, quality_score * 10,
            furthest_stage=furthest_stage if isinstance(furthest_stage, int) else -1,
            disqualified=bool(disqualified),
        ),
        "product_intel": {"insights": [], "jtbd": {"functional": "", "emotional": "", "trigger": ""}},
        "recommendations": [],
        "loss_reason": loss_reason,
        "loss_layer": loss_layer,
        "summary": summary,
    }
