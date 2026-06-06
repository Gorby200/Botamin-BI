"""Single-pass LLM integration point for the pipeline.

Replaces the former three-tier orchestrator. The pipeline now makes exactly ONE LLM
call per selected dialogue (pipeline/llm/analyze.py), cached on disk. The Tier-1 batch
screen and the transcript-re-reading Tier-3 are gone: everything the LLM judges
(stages, patterns, V4 quality layers, product-intel) comes from that single pass, and
ALL numbers (funnel, rates, distributions, frequencies, quality total/grade/outcome/gap)
are computed deterministically downstream.

The deterministic classifier (pipeline/stages.py) remains the failsafe: non-selected
calls and any call the LLM could not parse keep their deterministic analysis. Both
engines emit the SAME contract, so metrics.py is source-agnostic.
"""
from __future__ import annotations

import logging

from pipeline.config import settings
from pipeline.llm.client import get_client
from pipeline.llm.analyze import run_analysis

logger = logging.getLogger(__name__)


def _select_for_llm(features: list[dict], scope: str) -> list[int]:
    """Return indices of calls to send to the LLM under the given scope.

    - off:    none
    - full:   every connected call
    - sample: deterministic every-k-th connected call (reproducible, no RNG)
    - focus:  connected substantive dialogues only (>= MIN_CLIENT_TURNS client turns)
    """
    if scope == "off":
        return []
    connected = [i for i, f in enumerate(features)
                 if f.get("analysis", {}).get("connected", False)]
    if scope == "full":
        return connected
    if scope == "sample":
        k = max(1, len(connected) // max(settings.LLM_SAMPLE_SIZE, 1))
        return connected[::k][: settings.LLM_SAMPLE_SIZE]
    # focus (default)
    return [i for i in connected
            if features[i].get("client_turns", 0) >= settings.MIN_CLIENT_TURNS]


def integrate_with_pipeline(
    features: list[dict],
    llm_scope: str = "focus",
) -> tuple[list[dict], dict]:
    """Run the single LLM pass over the selected scope and merge results into features.

    Returns (features_with_llm, llm_status). Non-selected calls keep deterministic
    analysis; selected calls that the LLM parsed are replaced with the richer contract.
    """
    llm_status = {
        "configured": settings.llm_configured,
        "provider": settings.primary_provider,
        "scope": llm_scope,
        "mode": "deterministic",          # -> "llm_single_pass" when the LLM runs
        "available": False,
        "calls_selected": 0,
        "calls_analyzed": 0,
        "note": "",
    }

    if llm_scope == "off":
        llm_status["note"] = "LLM отключён (scope=off) — детерминированный анализ."
        return features, llm_status

    client = get_client()
    if not client.available:
        llm_status["note"] = "LLM-провайдер недоступен — детерминированный анализ."
        return features, llm_status

    llm_status["available"] = True
    selected = _select_for_llm(features, llm_scope)
    if not selected:
        llm_status["note"] = f"Под scope '{llm_scope}' не выбрано ни одного звонка."
        return features, llm_status

    logger.info("LLM single pass: %d/%d calls selected (scope=%s)",
                len(selected), len(features), llm_scope)
    calls = [{"id": f"c_{i:05d}", "turns": features[i]["turns"]} for i in selected]

    try:
        results = run_analysis(calls)
    except Exception as e:  # pragma: no cover
        logger.error("Single-pass LLM analysis failed: %s", e)
        llm_status["note"] = f"LLM-анализ упал: {e}. Использован детерминированный."
        return features, llm_status

    for i in selected:
        cid = f"c_{i:05d}"
        if cid in results:
            features[i]["analysis"] = results[cid]

    llm_status["mode"] = "llm_single_pass"
    llm_status["calls_selected"] = len(selected)
    llm_status["calls_analyzed"] = len(results)
    if not results:
        llm_status["note"] = "LLM не вернул ни одного результата — детерминированный фолбэк."
    return features, llm_status
