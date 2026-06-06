"""Two-layer metric engine (the corrected methodology).

The old metrics.py computed a flat tree off a broken classifier (NSM=0, S2->S3=86%).
This version implements the methodology the PO approved (option 1A):

  LAYER 0 — REACH (context, NOT fixable by the prompt)
      dials -> connect -> engage. Telephony/dialer/ASR territory.
  LAYER 1 — CONVERSATION FUNNEL (controllable, the prompt)
      S0 contact -> S1 consent -> S2 offer -> S3 meeting -> S4 qualified,
      every step CLIENT-GROUNDED. NSM = QMR computed honestly with variants.
  LAYER 2 — QUALITY / VOICE (leading indicators)
      responsiveness, ASR-breakdown rate, talk-share, monologue, repair.
  GUARDRAILS — what must not break while moving the drivers.
  LOSS ATTRIBUTION — every lost call tagged context vs controllable.

Every metric is wrapped by `metric()` which attaches threshold bands + a dynamic
Russian verdict + comment, so the dashboard can colour it and a CEO can read WHY.
Thresholds are documented constants (orienting values for cold B2B outbound voice),
tweakable here and explained on the Methodology page.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import pandas as pd


def _safe_div(a, b) -> float:
    return round(a / b, 4) if b else 0.0


def pctint(v) -> str:
    return f"{round(v * 100)}%"


LOSS_REASON_LABELS = {
    "no_answer": "Не дозвонились",
    "instant_hangup": "Бросил на приветствии (молча)",
    "instant_brushoff": "Рефлекторный сброс («что?/нет»)",
    "asr_breakdown": "Обвал связи / ASR",
    "refused": "Явный отказ",
    "disqualified": "Бот дисквалифицировал лида",
    "objection_unhandled": "Возражение не отработано",
    "no_qualification": "Встреча без квалификации",
    "no_close": "Оффер донесён, но нет закрытия",
    "pitch_no_traction": "Согласие есть, питч не зацепил",
    "opener_no_consent": "Вступил в разговор, но не дал согласия",
    "reached_goal": "Цель достигнута",
    "other": "Прочее",
}
LOSS_LAYER_LABELS = {"context": "Контекст (связь/дозвон)", "controllable": "Управляемое (промпт)", "none": "—"}


# ─── Threshold catalogue (DEFAULTS only) ────────────────────────────────────
# These are orienting DEFAULTS for cold B2B outbound voice. They are NOT the
# source of truth at render time: the pipeline emits them as data, and the
# Settings page lets the analyst edit/auto-derive them; the frontend re-bands live.
# Each entry: (good, ok, direction). higher = higher-is-better.
TH = {
    "connect_rate":        (0.60, 0.40, "higher"),
    "engage_rate":         (0.20, 0.10, "higher"),
    "conversation_rate":   (0.12, 0.06, "higher"),
    "early_drop_rate":     (0.30, 0.50, "lower"),
    "consent_rate":        (0.50, 0.30, "higher"),
    "offer_rate":          (0.55, 0.35, "higher"),
    "meeting_rate_drv":    (0.30, 0.15, "higher"),
    "qual_rate":           (0.50, 0.30, "higher"),
    "qmr":                 (0.15, 0.07, "higher"),
    "meeting_rate":        (0.20, 0.10, "higher"),
    "responsiveness":      (0.80, 0.60, "higher"),
    "asr_breakdown_rate":  (0.10, 0.20, "lower"),
    "bot_talk_share":      (0.65, 0.75, "lower"),
    "repair_rate":         (0.15, 0.30, "lower"),
    "quality_score":       (0.55, 0.40, "higher"),
    "meeting_quality":     (0.60, 0.40, "higher"),
    "disqualified_share":  (0.15, 0.30, "lower"),
    "complaint_rate":      (0.02, 0.05, "lower"),
    "over_pressure":       (0.05, 0.10, "lower"),
    "aht":                 (180,  300,  "lower"),
}

# Human label + fmt + group for the Settings page (so thresholds are editable data).
TH_META = {
    "connect_rate":       ("Дозвон — бот заговорил", "pct", "Reach"),
    "engage_rate":        ("Ответил живой человек", "pct", "Reach"),
    "conversation_rate":  ("Состоялся разговор (cold→warm)", "pct", "Reach"),
    "early_drop_rate":    ("Отвал на приветствии", "pct", "Reach"),
    "consent_rate":       ("S0→S1 · Согласие", "pct", "Воронка"),
    "offer_rate":         ("S1→S2 · Оффер донесён", "pct", "Воронка"),
    "meeting_rate_drv":   ("S2→S3 · Встреча", "pct", "Воронка"),
    "qual_rate":          ("S3→S4 · Квалификация", "pct", "Воронка"),
    "qmr":                ("QMR · Северная звезда", "pct", "Цель"),
    "meeting_rate":       ("Meeting Rate (S3/S1)", "pct", "Цель"),
    "responsiveness":     ("Отзывчивость бота", "ratio", "Качество"),
    "asr_breakdown_rate": ("Обвал связи / ASR", "pct", "Качество"),
    "bot_talk_share":     ("Доля речи бота", "ratio", "Качество"),
    "repair_rate":        ("Доля переспросов", "pct", "Качество"),
    "quality_score":      ("Качество ведения диалога", "ratio", "Качество"),
    "meeting_quality":    ("Полнота квалификации на встречах", "pct", "Guardrails"),
    "disqualified_share": ("Доля дисквалификаций", "pct", "Guardrails"),
    "complaint_rate":     ("Жалобы / «не звоните»", "pct", "Guardrails"),
    "over_pressure":      ("Избыточное давление после отказа", "pct", "Guardrails"),
    "aht":                ("Средняя длительность разговора", "sec", "Guardrails"),
}


def threshold_catalogue() -> list[dict]:
    """Editable threshold defaults as data (consumed by the Settings page)."""
    out = []
    for key, (good, ok, direction) in TH.items():
        label, fmt, group = TH_META.get(key, (key, "pct", "Прочее"))
        out.append({"key": key, "label": label, "fmt": fmt, "group": group,
                    "good": good, "ok": ok, "direction": direction})
    return out


def _band(value: float, key: str) -> str:
    if key not in TH:
        return "neutral"
    good, ok, direction = TH[key]
    if direction == "higher":
        return "good" if value >= good else "ok" if value >= ok else "bad"
    else:
        return "good" if value <= good else "ok" if value <= ok else "bad"


def metric(
    mid: str, name: str, value, *, key: str | None = None, fmt: str = "pct",
    desc: str = "", why: str = "", comment: dict | None = None,
    numerator: int | None = None, denominator: int | None = None,
) -> dict:
    """Wrap a raw value into a UI-ready metric with band + dynamic verdict.

    Emits BOTH the resolved band/comment (so the static JSON works out of the box)
    AND the raw inputs the frontend needs to RE-band live when the user edits
    thresholds on the Settings page: `thr_key`, full `comments` map, `thresholds`.
    """
    band = _band(value, key) if key else "neutral"
    comment = comment or {}
    verdict_text = comment.get(band, "")
    th = TH.get(key) if key else None
    return {
        "id": mid,
        "name": name,
        "value": value,
        "thr_key": key,                   # which threshold drives this metric
        "comments": comment,              # full {good,ok,bad} map for live re-banding
        "fmt": fmt,                       # pct | ratio | int | sec | float
        "band": band,                     # good | ok | bad | neutral
        "verdict": {"good": "Хорошо", "ok": "Приемлемо", "bad": "Требует внимания",
                    "neutral": ""}[band],
        "comment": verdict_text,
        "desc": desc,
        "why": why,
        "thresholds": {"good": th[0], "ok": th[1], "direction": th[2]} if th else None,
        "numerator": numerator,
        "denominator": denominator,
    }


# ───────────────────────────────────────────────────────────────────────────
def compute_metrics(df: pd.DataFrame) -> dict:
    """Compute the full two-layer metric model from the enriched DataFrame.

    Expects columns produced by build.py: connected, furthest_stage, outcome,
    disqualified, loss_layer, asr_breakdown, asr_severity, responsiveness,
    repair_attempts, bot_talk_share, longest_bot_monologue, quality_score,
    duration_sec, hour, dow, bot_turns, client_turns, objections, bot_patterns.
    """
    dials = len(df)

    # ── LAYER 0: REACH (three escalating gates) ─────────────────────────────
    has_dialogue = df["has_dialogue"]
    responded = df["client_turns"] >= 1            # made ANY sound
    connected = df["connected"]                     # said something SUBSTANTIVE
    n_opener = int(has_dialogue.sum())
    n_responded = int(responded.sum())
    n_conv = int(connected.sum())
    n_noise = int((responded & ~connected).sum())   # picked up, only reflexive noise

    connect_rate = _safe_div(n_opener, dials)
    response_rate = _safe_div(n_responded, dials)
    conversation_rate = _safe_div(n_conv, dials)
    noise_share = _safe_div(n_noise, n_responded)

    reach = {
        "dials": dials,
        "engaged": n_conv,
        "responded": n_responded,
        "metrics": [
            metric("connect_rate", "Дозвон — бот заговорил", connect_rate,
                   key="connect_rate", numerator=n_opener, denominator=dials,
                   desc="Доля номеров, где бот дозвонился и начал говорить (опенер прозвучал).",
                   why="Отделяет проблему дозвона от диалога. Низкий — вопрос к диалеру/базе, не к промпту.",
                   comment={"good": "Дозвон в норме — узкое место не здесь.",
                            "ok": "Дозвон средний: часть базы недоступна. Контролируйте качество/свежесть базы.",
                            "bad": "Низкий дозвон — теряем контакты до разговора. Зона диалера/базы."}),
            metric("response_rate", "Ответил живой человек", response_rate,
                   key="engage_rate", numerator=n_responded, denominator=dials,
                   desc="Доля номеров, где клиент произнёс хоть что-то (включая рефлекторное «алло?/что?»).",
                   why="Это ещё НЕ разговор. Важно отделить «издал звук» от реального диалога ниже.",
                   comment={"good": "Высокая доля поднявших трубку и ответивших.",
                            "ok": "Типичная для холода доля ответивших.",
                            "bad": "Мало кто отвечает — проверьте время дозвона, АОН, базу."}),
            metric("conversation_rate", "Состоялся разговор (cold→warm)", conversation_rate,
                   key="conversation_rate", numerator=n_conv, denominator=dials,
                   desc="Доля набранных номеров, где клиент сказал хотя бы одну СОДЕРЖАТЕЛЬНУЮ реплику (не «алло/что/нет»).",
                   why="Истинная база воронки и главный cold→warm-показатель. Всё качество промпта меряется ОТ неё. "
                       f"Из {n_responded} ответивших {pctint(noise_share)} — лишь рефлекторный шум, а не диалог.",
                   comment={"good": "Высокая для холода доля реальных разговоров — база тёплая/отобранная.",
                            "ok": "Доля реальных разговоров в норме для холодного аутбаунда по отобранной базе.",
                            "bad": "Мало реальных разговоров: либо база холодная, либо опенер не цепляет за первые секунды."}),
        ],
    }

    # base for the controllable funnel = REAL conversations (substantive)
    conv = df[connected].copy()
    base = len(conv)

    # ── LAYER 1: FUNNEL (client-grounded) ───────────────────────────────────
    def at_least(k):
        return int((conv["furthest_stage"] >= k).sum())

    n_s0 = base                 # contact (engaged)
    n_s1 = at_least(1)          # consent
    n_s2 = at_least(2)          # offer engaged
    n_s3 = at_least(3)          # meeting agreed
    n_s4 = at_least(4)          # qualified
    n_disq = int(conv["disqualified"].sum()) if base else 0
    n_s4_net = int(((conv["furthest_stage"] >= 4) & (~conv["disqualified"])).sum()) if base else 0

    stage_counts = {"S0": n_s0, "S1": n_s1, "S2": n_s2, "S3": n_s3, "S4": n_s4}
    stage_labels = {"S0": "Контакт", "S1": "Согласие", "S2": "Оффер донесён",
                    "S3": "Встреча", "S4": "Квалификация"}

    funnel = []
    order = ["S0", "S1", "S2", "S3", "S4"]
    for i, s in enumerate(order):
        prev = stage_counts[order[i - 1]] if i > 0 else base
        cnt = stage_counts[s]
        conv_from_prev = _safe_div(cnt, prev) if i > 0 else 1.0
        # drop attribution at this stage (calls whose furthest == previous stage)
        if i > 0:
            dropped_here = conv[conv["furthest_stage"] == (i - 1)]
            attr = {
                "client_hangup": int((dropped_here["end_attribution"] == "client_hangup").sum()),
                "bot_hangup": int((dropped_here["end_attribution"] == "bot_hangup").sum()),
                "technical": int((dropped_here["end_attribution"].isin(["technical", ""])).sum()),
                "context_loss": int((dropped_here["loss_layer"] == "context").sum()),
                "controllable_loss": int((dropped_here["loss_layer"] == "controllable").sum()),
            }
            dropped_abs = prev - cnt
        else:
            attr = {}
            dropped_abs = 0
        funnel.append({
            "stage": s, "label": stage_labels[s], "count": cnt,
            "conversion_from_prev": round(conv_from_prev, 4),
            "share_of_engaged": _safe_div(cnt, base),
            "dropped_abs": dropped_abs,
            "drop_attribution": attr,
        })

    # ── Drivers (the 4 controllable transition conversions) ─────────────────
    cr01 = _safe_div(n_s1, n_s0)
    cr12 = _safe_div(n_s2, n_s1)
    cr23 = _safe_div(n_s3, n_s2)
    cr34 = _safe_div(n_s4, n_s3)
    driver_specs = [
        ("CR0_1", "S0→S1 · Согласие", cr01, "opener", "consent_rate", n_s0, n_s1,
         "Доля состоявшихся разговоров, где клиент дал согласие слушать.",
         "Меряет силу опенера: цепляет ли первая реплика и просьба о согласии."),
        ("CR1_2", "S1→S2 · Оффер донесён", cr12, "offer", "offer_rate", n_s1, n_s2,
         "Доля согласившихся, кто реально услышал и среагировал на оффер.",
         "Меряет качество подачи оффера: понятно ли, не занудно ли, есть ли диалог."),
        ("CR2_3", "S2→S3 · Встреча", cr23, "closing", "meeting_rate_drv", n_s2, n_s3,
         "Доля услышавших оффер, кто СОГЛАСИЛСЯ на встречу (по словам клиента).",
         "Меряет силу закрытия: умеет ли бот предложить шаг и снять сопротивление."),
        ("CR3_4", "S3→S4 · Квалификация", cr34, "qualification", "qual_rate", n_s3, n_s4,
         "Доля согласившихся на встречу, кто ответил на квалифицирующие вопросы.",
         "Меряет качество квалификации: вплетена ли в контекст, не «допрос» ли."),
    ]
    drivers = []
    for did, label, val, block, key, vin, vout, desc, why in driver_specs:
        drivers.append({
            **metric(did, label, val, key=key, numerator=vout, denominator=vin,
                     desc=desc, why=why,
                     comment={"good": "Сильное звено — не первый кандидат на правку.",
                              "ok": "Среднее звено: есть резерв, но не самое узкое место.",
                              "bad": "Слабое звено воронки — приоритет для гипотез и A/B."}),
            "prompt_block": block,
            "volume_in": vin, "volume_out": vout,
            **_ab_planning(val),
        })

    # ── NSM: QMR (honest, with variants) ────────────────────────────────────
    qmr = _safe_div(n_s4, n_s1)                 # primary: qualified / consented (S1)
    qmr_net = _safe_div(n_s4_net, n_s1)         # excluding bot-disqualified leads
    meeting_rate = _safe_div(n_s3, n_s1)        # meetings / consented
    qmr_per_engaged = _safe_div(n_s4, base)     # qualified / engaged
    qmr_per_dial = _safe_div(n_s4, dials)       # qualified / all dials

    nsm = {
        **metric("QMR", "Qualified Meeting Rate", qmr, key="qmr",
                 numerator=n_s4, denominator=n_s1,
                 desc="Доля согласившихся разговоров (S1), доведённых до встречи С пройденной квалификацией.",
                 why="Северная звезда проекта: считает только встречи с квалифицированным лидом — "
                     "то, что реально кормит отдел продаж, а не «мусорные» встречи. Знаменатель S1 "
                     "отделяет качество промпта от проблем дозвона.",
                 comment={"good": "Здоровая доля качественных встреч на состоявшийся разговор.",
                          "ok": "Поток качественных встреч есть, но ниже цели — ищите узкое звено в драйверах.",
                          "bad": "Мало квалифицированных встреч на разговор: смотрите, где рвётся воронка (драйверы)."}),
        "variants": {
            "qmr_net": {"label": "QMR без дисквалифицированных", "value": qmr_net,
                        "hint": "Исключает лидов, которых бот сам отсёк (база мала и т.п.)."},
            "meeting_rate": {"label": "Meeting Rate (S3/S1)", "value": meeting_rate,
                             "hint": "Все встречи на согласившийся разговор, без требования квалификации."},
            "qmr_per_engaged": {"label": "QMR на разговор (S4/S0)", "value": qmr_per_engaged,
                                "hint": "Знаменатель — все состоявшиеся разговоры."},
            "qmr_per_dial": {"label": "QMR на набор (S4/всё)", "value": qmr_per_dial,
                             "hint": "Знаменатель — все набранные номера. Сюда «подмешан» дозвон."},
        },
        "counts": {"engaged": base, "consent": n_s1, "meeting": n_s3,
                   "qualified": n_s4, "qualified_net": n_s4_net, "disqualified": n_disq},
    }

    # ── LAYER 2: QUALITY / VOICE ─────────────────────────────────────────────
    multi = conv[conv["bot_turns"] >= 2] if base else conv
    avg_resp = round(float(multi["responsiveness"].mean()), 3) if len(multi) else 0.0
    asr_rate = _safe_div(int(conv["asr_breakdown"].sum()), base)
    avg_talk = round(float(multi["bot_talk_share"].mean()), 3) if len(multi) else 0.0
    avg_mono = round(float(multi["longest_bot_monologue"].mean()), 1) if len(multi) else 0.0
    repair_rate = _safe_div(int((conv["repair_attempts"] > 0).sum()), base)
    avg_quality = round(float(conv["quality_score"].mean()), 3) if base else 0.0

    quality = {
        "metrics": [
            metric("responsiveness", "Отзывчивость бота", avg_resp, key="responsiveness", fmt="ratio",
                   desc="Насколько реплики бота отвечают на последнюю реплику клиента (0–1).",
                   why="Прокси «слышит ли бот». Падает, когда бот повторяет вопрос из-за нераспознавания.",
                   comment={"good": "Бот ведёт диалог, а не гонит скрипт.",
                            "ok": "Местами бот не реагирует на сказанное — проверьте обработку реплик.",
                            "bad": "Бот часто игнорирует/повторяет — диалог рвётся. Смотрите ASR и логику ответов."}),
            metric("asr_breakdown_rate", "Обвал связи/ASR", asr_rate, key="asr_breakdown_rate",
                   numerator=int(conv["asr_breakdown"].sum()), denominator=base,
                   desc="Доля разговоров с признаками проблем слышимости («не слышу», «алло», «что?»).",
                   why="Контекстная метрика №1. Высокая — промпт чинить бессмысленно, нужен телефон/ASR.",
                   comment={"good": "Связь в основном чистая.",
                            "ok": "Заметная доля звонков со сбоями слышимости — эскалируйте телефонии.",
                            "bad": "Каждый 5-й+ разговор рушится из-за связи. Это убивает конверсию ДО промпта."}),
            metric("bot_talk_share", "Доля речи бота", avg_talk, key="bot_talk_share", fmt="ratio",
                   desc="Доля слов, сказанных ботом, от всех слов в разговоре (talk-to-listen).",
                   why="Высокая доля = монолог, клиент не вовлечён. Здоровый диалог ближе к балансу.",
                   comment={"good": "Сбалансированный диалог — клиент успевает участвовать.",
                            "ok": "Бот говорит заметно больше клиента — разбейте оффер на ходы.",
                            "bad": "Бот доминирует в речи — это монолог-питч, а не диалог."}),
            metric("repair_rate", "Доля разговоров с переспросами", repair_rate, key="repair_rate",
                   numerator=int((conv["repair_attempts"] > 0).sum()), denominator=base,
                   desc="Доля разговоров, где клиент переспрашивал/не расслышал хотя бы раз.",
                   why="Прокси фрустрации от ASR. Коррелирует с ранним отвалом.",
                   comment={"good": "Переспросы редки.",
                            "ok": "Переспросы заметны — частично ASR, частично длинные реплики бота.",
                            "bad": "Частые переспросы — клиенты не понимают бота. Связь + длина реплик."}),
            metric("quality_score", "Качество ведения диалога", avg_quality, key="quality_score", fmt="ratio",
                   desc="Композитная оценка качества диалога (продвижение + отзывчивость), 0–1.",
                   why="Опережающий индикатор: меняется раньше конверсии, помогает быстрее оценивать A/B.",
                   comment={"good": "Бот в среднем ведёт диалоги качественно.",
                            "ok": "Среднее качество — есть системные провисания (см. паттерны).",
                            "bad": "Низкое качество ведения — много негативных паттернов/обрывов."}),
        ],
    }

    # ── GUARDRAILS ───────────────────────────────────────────────────────────
    meeting_quality = _safe_div(n_s4, n_s3)
    disq_share = _safe_div(n_disq, n_s3)
    complaint_rate = _safe_div(int(conv["complaint_signal"].sum()), base) if "complaint_signal" in conv else 0.0
    over_pressure = _over_pressure_rate(conv, base)
    aht = round(float(conv["duration_sec"].mean()), 1) if base else 0.0

    guardrails = [
        metric("meeting_quality", "Полнота квалификации на встречах", meeting_quality,
               key="meeting_quality", numerator=n_s4, denominator=n_s3,
               desc="Доля назначенных встреч, на которых пройдена квалификация.",
               why="Контр-метрика к «гонке за встречами»: бот не должен набивать пустые встречи.",
               comment={"good": "Встречи в основном квалифицированы.",
                        "ok": "Часть встреч без квалификации — риск мусорных встреч.",
                        "bad": "Много встреч без квалификации — встречи могут быть мусорными."}),
        metric("disqualified_share", "Доля дисквалификаций среди встреч", disq_share,
               key="disqualified_share", numerator=n_disq, denominator=n_s3,
               desc="Доля встреч, где бот сам отсёк лида (база мала и т.п.).",
               why="Показывает, не таргетируем ли не ту базу: высокий — проблема сегмента, не промпта.",
               comment={"good": "Дисквалификаций мало.",
                        "ok": "Заметная дисквалификация — проверьте ICP/сегмент базы.",
                        "bad": "Много дисквалификаций — звоним не той базе (вопрос к таргетингу, не промпту)."}),
        metric("complaint_rate", "Жалобы / «не звоните»", complaint_rate, key="complaint_rate",
               desc="Доля разговоров с явным негативом/просьбой не звонить.",
               why="Репутационный guardrail: рост при агрессивном промпте недопустим.",
               comment={"good": "Негатив в пределах нормы.",
                        "ok": "Негатив подрос — следите при ужесточении промпта.",
                        "bad": "Высокий негатив — риск для бренда и блокировок номеров."}),
        metric("over_pressure", "Избыточное давление после отказа", over_pressure, key="over_pressure",
               desc="Доля разговоров, где бот давит после явного отказа клиента.",
               why="Guardrail при усилении закрытия: нельзя поднимать встречи ценой агрессии.",
               comment={"good": "Бот корректно отступает после отказа.",
                        "ok": "Местами передавливает — точечно поправить.",
                        "bad": "Бот системно давит после отказа — источник жалоб."}),
        metric("aht", "Средняя длительность разговора", aht, key="aht", fmt="sec",
               desc="Средняя длительность состоявшегося разговора, сек.",
               why="Экономика: слишком длинные разговоры дороги; слишком короткие — не доносят оффер.",
               comment={"good": "Длительность в здоровом коридоре.",
                        "ok": "Разговоры длинноваты — проверьте затянутость питча.",
                        "bad": "Очень длинные разговоры — дорого и обычно из-за ASR-петель/монологов."}),
    ]

    # ── LOSS ATTRIBUTION (context vs controllable) ──────────────────────────
    lost = conv[conv["furthest_stage"] < 4]
    loss_layer_counts = lost["loss_layer"].value_counts().to_dict()
    loss_reason_counts = lost["loss_reason"].value_counts().to_dict()
    n_context = int(loss_layer_counts.get("context", 0))
    n_controllable = int(loss_layer_counts.get("controllable", 0))
    loss_attribution = {
        "context": n_context,
        "controllable": n_controllable,
        "context_share": _safe_div(n_context, len(lost)),
        "controllable_share": _safe_div(n_controllable, len(lost)),
        "by_reason": [{"reason": k, "label": LOSS_REASON_LABELS.get(k, k), "count": int(v)}
                      for k, v in sorted(loss_reason_counts.items(), key=lambda x: -x[1])],
    }

    # ── BOTTLENECK (largest CONTROLLABLE relative drop) ─────────────────────
    bottleneck = _bottleneck(funnel, drivers)

    # ── Outcomes / distributions ────────────────────────────────────────────
    outcomes = _outcomes(df)
    time_heatmap = _time_heatmap(conv)
    duration_distribution = _duration_dist(conv)

    return {
        "reach": reach,
        "nsm": nsm,
        "funnel": funnel,
        "drivers": drivers,
        "quality": quality,
        "guardrails": guardrails,
        "loss_attribution": loss_attribution,
        "bottleneck": bottleneck,
        "outcomes": outcomes,
        "time_heatmap": time_heatmap,
        "duration_distribution": duration_distribution,
        "thresholds_defaults": threshold_catalogue(),
    }


def _ab_planning(baseline: float) -> dict:
    """Rough MDE + sample-size for an A/B at this conversion (80% power, α=0.05)."""
    mde = 0.05 if baseline > 0.1 else 0.03
    p1, p2 = baseline, baseline + mde
    if 0 < p1 < 1 and 0 < p2 < 1:
        pooled = (p1 + p2) / 2
        n = math.ceil(2 * pooled * (1 - pooled) * (1.96 + 0.84) ** 2 / (p2 - p1) ** 2)
    else:
        n = 0
    return {"mde_pp": round(mde * 100, 1), "sample_needed": n}


def _over_pressure_rate(conv: pd.DataFrame, base: int) -> float:
    if not base:
        return 0.0
    cnt = 0
    for _, row in conv.iterrows():
        pats = row.get("bot_patterns", [])
        if isinstance(pats, list) and any(
            isinstance(p, dict) and p.get("id") in ("PSY-094", "PSY-201") for p in pats
        ) and row.get("outcome") == "refused":
            cnt += 1
    return _safe_div(cnt, base)


def _bottleneck(funnel: list[dict], drivers: list[dict]) -> dict:
    """Binding constraint = biggest OPPORTUNITY, not the lowest rate.

    A low conversion on a low-volume tail (e.g. 46->7 qualification) is NOT where to
    spend effort: even a big % uplift yields ~zero NSM because few people reach it.
    Opportunity sizes the realistic NSM gain from fixing each stage:
        opportunity = volume_in * achievable_uplift(value) * downstream_pass_through
    This is the same logic the backlog uses, so the headline matches the #1 hypothesis.
    """
    if not drivers:
        return {}
    # Headline bottleneck = largest ABSOLUTE drop (where most humans are lost).
    # This is volume-honest and intuitive; the backlog separately ranks fixes by
    # ROI (effort + downstream pass-through), which can differ from this headline.
    best = max(drivers, key=lambda d: d["volume_in"] - d["volume_out"])
    stage_map = {"CR0_1": ("S0", "S1"), "CR1_2": ("S1", "S2"),
                 "CR2_3": ("S2", "S3"), "CR3_4": ("S3", "S4")}
    s_from, s_to = stage_map.get(best["id"], ("S0", "S1"))
    return {
        "driver_id": best["id"],
        "label": best["name"],
        "stage_from": s_from, "stage_to": s_to,
        "conversion": best["value"],
        "dropped_abs": best["volume_in"] - best["volume_out"],
        "prompt_block": best["prompt_block"],
        "rationale": "Узкое место по абсолютному числу потерянных клиентов. "
                     "Приоритет правок (с учётом усилия и прохождения вниз по воронке) — в Бэклоге.",
    }


def _outcomes(df: pd.DataFrame) -> list[dict]:
    mapping = [
        ("qualified", "Полная квалификация", 5),
        ("meeting", "Назначена встреча", 4),
        ("offer_engaged", "Оффер донесён", 3),
        ("consent", "Получено согласие", 2),
        ("contact_only", "Только контакт", 1),
        ("refused", "Отказ", 1),
        ("no_contact", "Нет контакта", 0),
    ]
    out = []
    for key, label, score in mapping:
        out.append({"outcome": label, "key": key,
                    "count": int((df["outcome"] == key).sum()), "score": score})
    return out


def _time_heatmap(conv: pd.DataFrame) -> list[dict]:
    rows = []
    if "hour" not in conv.columns or "dow" not in conv.columns:
        return rows
    for dow in range(7):
        for hour in range(24):
            mask = (conv["dow"] == dow) & (conv["hour"] == hour)
            n = int(mask.sum())
            if n:
                rows.append({
                    "dow": dow, "hour": hour, "calls": n,
                    "advanced": int((mask & (conv["furthest_stage"] >= 3)).sum()),
                })
    return rows


def _duration_dist(conv: pd.DataFrame) -> list[dict]:
    out = []
    if "duration_sec" not in conv.columns:
        return out
    buckets = [(0, 10), (10, 30), (30, 60), (60, 120), (120, 300), (300, 600), (600, 99999)]
    for lo, hi in buckets:
        cnt = int(((conv["duration_sec"] >= lo) & (conv["duration_sec"] < hi)).sum())
        out.append({"bucket_sec": f"{lo}-{hi}" if hi < 99999 else f"{lo}+", "count": cnt})
    return out
