"""Bot-adapted call-quality methodology (V4) + deterministic scoring.

Adapted from a human-salesperson V4 scorecard (prior project) to a voice BOT making
short B2B cold calls. The bot's job is a 4-task ladder (opener→consent→offer→meeting
→qualify), not a full 15-stage human sales call, so the Macro scenario is compressed
to what the bot actually does.

THE NUMBER/JUDGEMENT SPLIT (core principle):
  - The LLM (per call) supplies ONLY three 0–10 layer scores — Macro, Micro, Overlap —
    its judgement of HOW WELL the bot executed each layer, with evidence in the patterns.
  - Python (here) owns ALL arithmetic: the weighted TOTAL, the letter grade, the
    deterministic OUTCOME (how far the client actually advanced — from furthest_stage),
    and the GAP (quality − outcome) that drives prompt-optimization priorities.

This keeps quality scoring trustworthy: the model never invents a final number.
"""
from __future__ import annotations

# ── Macro scenario (what the bot does), weights sum to 1.0 ───────────────────
MACRO_STAGES = [
    {"key": "opener", "name": "Опенер и получение согласия", "weight": 0.20},
    {"key": "rapport", "name": "Контакт/раппорт", "weight": 0.10},
    {"key": "offer", "name": "Донесение оффера (ценность)", "weight": 0.20},
    {"key": "discovery", "name": "Выявление потребности/боли", "weight": 0.10},
    {"key": "objection", "name": "Отработка возражений", "weight": 0.15},
    {"key": "closing", "name": "Закрытие на встречу", "weight": 0.20},
    {"key": "qualification", "name": "Квалификация лида", "weight": 0.05},
]

MICRO_CATEGORIES = [
    {"key": "responsiveness", "name": "Отзывчивость (отвечает по сути на реплику)"},
    {"key": "pacing", "name": "Темп/длина реплик (без затянутых монологов)"},
    {"key": "listening", "name": "Активное слушание (подхватывает слова клиента)"},
    {"key": "word_choice", "name": "Выбор слов (простой язык, без жаргона)"},
    {"key": "empathy", "name": "Эмоц. интеллект (считывает интерес/раздражение)"},
]

OVERLAP_TECHNIQUES = [
    "Yes-set / лестница согласий", "Альтернативное закрытие (double-bind)",
    "Взаимность (ценность вперёд)", "Социальное доказательство",
    "Пресуппозиция встречи", "Feel-Felt-Found", "ROI / бизнес-язык",
]

# Letter-grade bands on the 0–10 total (matches the prior project's V4 grading).
GRADE_BANDS = [
    (9.0, "A", "Эталон"),
    (7.0, "B", "Сильный"),
    (5.0, "C", "Базовый"),
    (3.0, "D", "Слабый"),
    (0.0, "F", "Критический"),
]

# Deterministic advancement score (0–10) per furthest client-confirmed stage.
# Mirrors the funnel: contact(0) → consent(1) → offer(2) → meeting(3) → qualified(4).
_OUTCOME_BY_STAGE = {-1: 0.0, 0: 1.0, 1: 2.5, 2: 4.0, 3: 8.0, 4: 10.0}


def _clamp10(v) -> float:
    try:
        return max(0.0, min(10.0, float(v)))
    except (TypeError, ValueError):
        return 0.0


def grade_for(total: float) -> tuple[str, str]:
    for threshold, letter, name in GRADE_BANDS:
        if total >= threshold:
            return letter, name
    return "F", "Критический"


def compute_quality_total(macro, micro, overlap) -> dict:
    """Weighted V4 total + grade. Python owns the formula; the LLM only judged layers."""
    macro, micro, overlap = _clamp10(macro), _clamp10(micro), _clamp10(overlap)
    total = round(0.70 * macro + 0.15 * micro + 0.15 * overlap, 2)
    letter, name = grade_for(total)
    return {
        "macro": round(macro, 2), "micro": round(micro, 2), "overlap": round(overlap, 2),
        "total": total, "grade": letter, "grade_name": name,
        "breakdown": {
            "macro_contribution": round(0.70 * macro, 2),
            "micro_contribution": round(0.15 * micro, 2),
            "overlap_contribution": round(0.15 * overlap, 2),
        },
    }


def compute_outcome(furthest_stage: int, disqualified: bool = False) -> float:
    """Deterministic 0–10 advancement score from the client-confirmed furthest stage."""
    try:
        fs = int(furthest_stage)
    except (TypeError, ValueError):
        fs = -1
    return _OUTCOME_BY_STAGE.get(max(-1, min(4, fs)), 0.0)


def compute_gap(quality_total: float, outcome: float) -> dict:
    """Gap = quality − outcome. Reveals where to focus prompt optimization.

      gap > +1.5  → bot executes well but does NOT convert → closing/base bottleneck.
      gap < −1.5  → client advances despite weak execution → warm/easy base or luck.
      otherwise   → quality matches outcome.
    """
    gap = round(quality_total - outcome, 2)
    eff = round(outcome / quality_total, 2) if quality_total > 0 else 0.0
    if gap > 1.5:
        interp = "Качество выше результата — узкое место в закрытии или нерелевантная база (хорошо ведёт, но не доводит до встречи)."
    elif gap < -1.5:
        interp = "Результат выше качества — тёплая/лёгкая база (клиент доходит несмотря на слабое ведение); промпт недоиспользует потенциал."
    else:
        interp = "Качество соответствует результату."
    return {"gap": gap, "efficiency_ratio": eff, "interpretation": interp}


def quality_from_layers(macro, micro, overlap, furthest_stage: int,
                        disqualified: bool = False) -> dict:
    """Assemble the full quality object from LLM layer scores + deterministic outcome/gap."""
    q = compute_quality_total(macro, micro, overlap)
    outcome = compute_outcome(furthest_stage, disqualified)
    q["outcome"] = outcome
    q["gap"] = compute_gap(q["total"], outcome)
    return q


def rubric_for_prompt() -> str:
    """RU instructions for the LLM: how to assign the three 0–10 layer scores.

    The model returns only macro/micro/overlap (0–10). It does NOT compute the total,
    grade, outcome or gap — Python does (so the headline number is never invented).
    """
    macro_lines = "\n".join(
        f"    - {s['name']} (вес {int(s['weight']*100)}%)" for s in MACRO_STAGES
    )
    micro_lines = "\n".join(f"    - {c['name']}" for c in MICRO_CATEGORIES)
    overlap_lines = ", ".join(OVERLAP_TECHNIQUES)
    return (
        "ОЦЕНКА КАЧЕСТВА ВЕДЕНИЯ (методика V4, 3 слоя). Верни ТРИ числа 0–10 — насколько "
        "ХОРОШО бот отработал каждый слой. Итоговый балл, грейд и разрыв посчитает система — "
        "ты числа НЕ выдумывай сверх этих трёх.\n"
        "  • macro (0–10): насколько качественно пройден сценарий звонка по этапам:\n"
        f"{macro_lines}\n"
        "    Оценивай только применимые этапы; не штрафуй за обрыв связи.\n"
        "  • micro (0–10): качество исполнения:\n"
        f"{micro_lines}\n"
        "  • overlap (0–10): уместность техник влияния "
        f"({overlap_lines}).\n"
        "Будь консервативен: высокий балл — только при явных доказательствах в репликах бота."
    )
