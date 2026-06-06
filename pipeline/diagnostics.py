"""Diagnostics: pattern audit, objection clustering, pitch effectiveness, backlog.

Consumes the unified analysis contract (per-call `bot_patterns` / `objections`
columns produced by either the deterministic classifier or the LLM). Aggregates
incidence, correlates patterns with advancement, and turns the leak picture into a
ranked backlog of prompt-correction hypotheses with A/B designs.
"""
from __future__ import annotations

import math
import re
from collections import Counter

import pandas as pd

# Human-readable names + polarity + impact for the pattern ids the engines emit.
PATTERN_META = {
    "PSY-010": ("Запрос разрешения в опенере", "positive", "high", "opener"),
    "PSY-047": ("Альтернативное закрытие", "positive", "critical", "closing"),
    "PSY-082": ("Feel-Felt-Found", "positive", "high", "offer"),
    "PSY-011": ("Питч в лоб в опенере", "negative", "critical", "opener"),
    "PSY-124": ("Затянутый монолог-питч", "negative", "critical", "offer"),
    "PSY-094": ("Игнорирование возражения", "negative", "critical", "offer"),
    "PSY-095": ("Преждевременная сдача", "negative", "critical", "closing"),
    "PSY-106": ("Нет закрытия (нет CTA)", "negative", "critical", "closing"),
    "PSY-200": ("ASR-петля (бот повторяется)", "negative", "critical", "context"),
    "PSY-201": ("Глухота к проблеме связи", "negative", "critical", "context"),
}

OBJECTION_GAP_MAP = {
    "price": "pricing", "no_need": "positioning", "have_alternative": "product",
    "no_time": "prompt", "no_budget": "pricing", "send_info": "prompt",
    "have_internal": "product", "not_priority": "positioning", "gatekeeper": "routing",
}

OBJECTION_LABELS = {
    "price": "Дорого / цена", "no_need": "Не нужно / не актуально",
    "have_alternative": "Уже есть решение", "no_time": "Нет времени / позже",
    "no_budget": "Нет бюджета", "send_info": "Пришлите на почту",
    "have_internal": "Делаем сами", "not_priority": "Не приоритет",
    "gatekeeper": "Не я решаю / секретарь",
}


def audit_bot_patterns(df: pd.DataFrame) -> list[dict]:
    """Incidence of each bot pattern + lift on advancement (reaching a meeting)."""
    conv = df[df["connected"]].copy()
    if conv.empty:
        return []
    total = len(conv)
    base_advance = float((conv["furthest_stage"] >= 3).mean())

    stats: dict[str, dict] = {}
    for _, row in conv.iterrows():
        advanced = row["furthest_stage"] >= 3
        seen = set()
        for p in (row.get("bot_patterns", []) or []):
            if not isinstance(p, dict):
                continue
            pid = p.get("id", "")
            if not pid or pid in seen:
                continue
            seen.add(pid)
            st = stats.setdefault(pid, {"count": 0, "advanced": 0})
            st["count"] += 1
            if advanced:
                st["advanced"] += 1

    results = []
    for pid, st in stats.items():
        name, polarity, impact, block = PATTERN_META.get(pid, (pid, "negative", "medium", "offer"))
        share = round(st["count"] / total, 4)
        lift = round(st["advanced"] / st["count"] - base_advance, 4) if st["count"] else 0.0
        weight = {"critical": 3, "high": 2, "medium": 1}.get(impact, 1)
        results.append({
            "psy_id": pid, "name": name, "polarity": polarity, "impact": impact,
            "prompt_block": block, "weight": weight, "share": share,
            "count": st["count"], "lift_on_advance": lift,
        })
    results.sort(key=lambda x: x["weight"] * x["share"], reverse=True)
    return results


def cluster_objections(df: pd.DataFrame) -> list[dict]:
    conv = df[df["connected"]].copy()
    if conv.empty:
        return []
    clusters: dict[str, dict] = {}
    for _, row in conv.iterrows():
        for o in (row.get("objections", []) or []):
            if not isinstance(o, dict):
                continue
            ot = o.get("type", "")
            if not ot:
                continue
            c = clusters.setdefault(ot, {
                "type": ot, "label": OBJECTION_LABELS.get(ot, ot),
                "gap": OBJECTION_GAP_MAP.get(ot, "prompt"),
                "count": 0, "verbatims": [], "by_stage": {},
            })
            c["count"] += 1
            q = (o.get("quote") or "")[:200]
            if q and len(c["verbatims"]) < 15:
                c["verbatims"].append(q)
            st = f"S{int(row['furthest_stage'])}" if row["furthest_stage"] >= 0 else "no_contact"
            c["by_stage"][st] = c["by_stage"].get(st, 0) + 1
    return sorted(clusters.values(), key=lambda x: x["count"], reverse=True)


def analyze_pitch(df: pd.DataFrame) -> dict:
    """Which bot sentences appear more in advancing vs non-advancing calls."""
    conv = df[df["connected"]].copy()
    if conv.empty:
        return {"resonated": [], "fell_flat": []}
    stayed = conv[conv["furthest_stage"] >= 2]
    left = conv[conv["furthest_stage"] < 2]

    def phrase_counter(frame):
        c = Counter()
        for _, row in frame.iterrows():
            for s in re.split(r"[.!?]\s*", str(row.get("bot_text", ""))):
                s = s.strip()
                if 25 < len(s) < 160:
                    c[s] += 1
        return c

    sc, lc = phrase_counter(stayed), phrase_counter(left)
    resonated = [{"phrase": p[:200], "stayed": n, "left": lc.get(p, 0)}
                 for p, n in sc.most_common(20) if n > lc.get(p, 0)][:5]
    fell_flat = [{"phrase": p[:200], "left": n, "stayed": sc.get(p, 0)}
                 for p, n in lc.most_common(20) if n > sc.get(p, 0)][:5]
    return {"resonated": resonated, "fell_flat": fell_flat}


# ───────────────────────────────────────────────────────────────────────────
INTERVENTION_MAP = {
    "opener": {
        "stage": "S0→S1",
        "interventions": [
            "Короче опенер: ценность в первой фразе, один да/нет на согласие (PSY-010).",
            "Снять «роботность» первой реплики, мягкая идентификация, меньше задержка.",
        ],
        "guardrails": ["complaint_rate", "early_drop_rate"],
        "effort": "low",
    },
    "offer": {
        "stage": "S1→S2",
        "interventions": [
            "Структура «боль→выгода→1 факт», без жаргона; чек-ин-вопрос после блока.",
            "Разбить питч на диалоговые ходы (снизить долю речи бота и монолог).",
        ],
        "guardrails": ["aht", "bot_talk_share"],
        "effort": "med",
    },
    "closing": {
        "stage": "S2→S3",
        "interventions": [
            "Альтернативное закрытие (PSY-047) вместо открытого вопроса о времени.",
            "Лестница отступления: демо → короткий созвон → материалы (без сдачи раньше времени, PSY-095).",
        ],
        "guardrails": ["over_pressure", "disqualified_share", "meeting_quality"],
        "effort": "med",
    },
    "qualification": {
        "stage": "S3→S4",
        "interventions": [
            "Вплести квалификацию в контекст встречи (не «допрос»): 1–2 вопроса максимум.",
            "Порядок вопросов от простого к сложному; объяснить, зачем спрашиваем.",
        ],
        "guardrails": ["aht", "meeting_quality"],
        "effort": "high",
    },
    "context": {
        "stage": "Контекст (связь/ASR)",
        "interventions": [
            "ЭСКАЛАЦИЯ В ТЕЛЕФОНИЮ/ASR: это не правится промптом. Проверить кодек/задержку/частоту дискретизации, добавить детектор «не слышу» с переносом звонка.",
        ],
        "guardrails": [],
        "effort": "med",
    },
}


def generate_backlog(drivers, nsm, funnel, pattern_audit, objection_clusters,
                     loss_attribution, base_conversations) -> list[dict]:
    """Rank prompt-correction hypotheses by expected NSM lift / effort.

    Opportunity sizing uses downstream pass-through: fixing a stage only yields
    NSM if the gained volume survives ALL downstream conversions.
    """
    hyps = []
    drivers_by_block = {d["prompt_block"]: d for d in drivers}
    driver_order = ["opener", "offer", "closing", "qualification"]

    # If context losses dominate, surface a context hypothesis first (honesty).
    context_share = loss_attribution.get("context_share", 0)
    if context_share >= 0.25:
        info = INTERVENTION_MAP["context"]
        hyps.append(_hyp(
            block="context", driver=None, info=info,
            expected_nsm_delta=0.0, achievable=0.0, pass_through=1.0,
            confidence=0.7, evidence_metric="loss_attribution.context_share",
            evidence_value=context_share, patterns=[], verbatims=[],
            note=f"{context_share*100:.0f}% потерь — на контекстном слое (связь/ASR). "
                 "Промпт здесь не двигает конверсию.",
        ))

    for block in driver_order:
        d = drivers_by_block.get(block)
        if not d:
            continue
        info = INTERVENTION_MAP[block]
        val = d["value"]
        vin = d["volume_in"]
        achievable = 0.10 if val < 0.3 else 0.08 if val < 0.5 else 0.05 if val < 0.7 else 0.03

        # downstream pass-through = product of conversions AFTER this driver
        idx = driver_order.index(block)
        downstream = [drivers_by_block[b]["value"] for b in driver_order[idx + 1:]
                      if b in drivers_by_block]
        pass_through = 1.0
        for r in downstream:
            pass_through *= max(r, 0.01)

        expected_nsm = round(vin * achievable * pass_through / max(base_conversations, 1) * 100, 2)
        pat_ev = [f"{p['psy_id']} {p['name']} (доля {p['share']*100:.0f}%, lift {p['lift_on_advance']:+.2f})"
                  for p in pattern_audit
                  if p["polarity"] == "negative" and p.get("prompt_block") == block][:3]
        verbatims = [v for oc in objection_clusters[:3] for v in oc.get("verbatims", [])[:1]][:4]
        hyps.append(_hyp(
            block=block, driver=d, info=info, expected_nsm_delta=expected_nsm,
            achievable=achievable, pass_through=round(pass_through, 4),
            confidence=0.6 if val > 0.1 else 0.4,
            evidence_metric=d["id"], evidence_value=val,
            patterns=pat_ev, verbatims=verbatims, note="",
        ))

    # Rank by expected NSM lift / effort
    effort_score = {"low": 1, "med": 2, "high": 3}
    hyps.sort(key=lambda h: h["expected_nsm_delta_pp"] / effort_score.get(h["effort"], 2), reverse=True)
    for i, h in enumerate(hyps):
        h["priority"] = i + 1
    return hyps


def _hyp(*, block, driver, info, expected_nsm_delta, achievable, pass_through,
         confidence, evidence_metric, evidence_value, patterns, verbatims, note) -> dict:
    intervention = info["interventions"][0]
    ab = _ab(driver["value"]) if driver else {"mde_pp": 0, "sample": 0, "duration_days": 0}
    return {
        "hypothesis": intervention,
        "alternatives": info["interventions"][1:],
        "prompt_block": block,
        "stage": info["stage"],
        "evidence": {"metric": evidence_metric, "value": evidence_value,
                     "patterns": patterns, "verbatims": verbatims, "note": note},
        "expected_driver_delta_pp": round(achievable * 100, 1),
        "downstream_pass_through": pass_through,
        "expected_nsm_delta_pp": expected_nsm_delta,
        "effort": info["effort"],
        "risk_guardrails": info["guardrails"],
        "confidence": confidence,
        "ab_design": {"variant": intervention[:90], "primary": evidence_metric, **ab},
        "priority": 0,
    }


def _ab(baseline: float) -> dict:
    mde = 0.05 if baseline > 0.1 else 0.03
    p1, p2 = baseline, baseline + mde
    if 0 < p1 < 1 and 0 < p2 < 1:
        pooled = (p1 + p2) / 2
        n = math.ceil(2 * pooled * (1 - pooled) * (1.96 + 0.84) ** 2 / (p2 - p1) ** 2)
    else:
        n = 0
    return {"mde_pp": round(mde * 100, 1), "sample": n, "duration_days": 0}
