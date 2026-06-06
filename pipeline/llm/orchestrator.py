"""Three-tier LLM orchestrator for Botamin BI pipeline.

This module integrates the three LLM analysis tiers:
- Tier 1: Batch rapid screening (40-50 calls per request)
- Tier 2: Targeted deep dive (flagged calls only)
- Tier 3: Aggregated research insights

DESIGN:
  1. Fail-safe: falls back to deterministic if LLM unavailable
  2. Cache-friendly: respects existing cache from analyze.py
  3. Progress tracking: logs progress for large batches
  4. Result merging: combines all tiers into unified output

USAGE:
    from pipeline.llm.orchestrator import analyze_with_tiers
    results = await analyze_with_tiers(calls, client)
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Optional

from pipeline.config import settings
from pipeline.llm.client import get_client
from pipeline.llm.batch import BatchAnalyzer, BatchResult
from pipeline.llm.analyze import run_analysis
from pipeline.llm.research import ResearchAnalyzer, run_research_analysis
from pipeline.llm.schemas import DetailedAnalysisOutput, unified_from_batch

logger = logging.getLogger(__name__)


async def analyze_with_tiers(
    calls: list[dict],
    use_tier3: bool = True,
    model: str = ""
) -> dict:
    """Run complete three-tier LLM analysis on calls.

    Args:
        calls: List of call dicts with "id", "turns", "duration_sec"
        use_tier3: Whether to run Tier 3 research analysis
        model: Optional model override

    Returns:
        Dict with:
        - tier1: Batch results for all calls
        - tier2: Detailed results for flagged calls
        - tier3: Research insights (if use_tier3)
        - merged: Unified results compatible with metrics.py
    """
    client = get_client()
    if not client.available:
        logger.warning("LLM unavailable, falling back to deterministic only")
        return {
            "status": "fallback",
            "tier1": None,
            "tier2": None,
            "tier3": None,
            "merged": {},
            "note": "LLM unavailable - using deterministic classification"
        }

    start_time = datetime.now()
    results = {
        "started_at": start_time.isoformat(),
        "total_calls": len(calls),
        "tier1": None,
        "tier2": None,
        "tier3": None,
        "merged": {}
    }

    # ── Tier 1: Batch Screening ────────────────────────────────────────────────
    logger.info("=" * 60)
    logger.info("TIER 1: Batch Analysis")
    logger.info("=" * 60)

    batcher = BatchAnalyzer(client, batch_size=settings.LLM_BATCH_SIZE if hasattr(settings, 'LLM_BATCH_SIZE') else 50)
    tier1_results = await batcher.analyze_all(calls, model)
    results["tier1"] = {k: v.to_dict() if hasattr(v, 'to_dict') else v for k, v in tier1_results.items()}

    successful_tier1 = sum(1 for r in tier1_results.values() if r.success)
    logger.info("Tier 1 complete: %d/%d successful", successful_tier1, len(tier1_results))

    # Convert to unified format for pipeline compatibility
    unified_tier1 = {}
    for call_id, batch_res in tier1_results.items():
        try:
            unified_tier1[call_id] = unified_from_batch(batch_res)
        except Exception as e:
            logger.warning("Failed to convert %s to unified: %s", call_id, e)

    results["merged"] = unified_tier1

    # ── Tier 2: Detailed Deep Dive ────────────────────────────────────────────
    flagged = [
        c for c in calls
        if tier1_results.get(c.get("id", ""), BatchResult(c.get("id", ""), -1, [], [], False, 0.0)).flag
    ]

    if flagged:
        logger.info("=" * 60)
        logger.info("TIER 2: Detailed Analysis (%d flagged calls)", len(flagged))
        logger.info("=" * 60)

        # Reuse existing run_analysis for compatibility
        tier2_payload = [{"id": c["id"], "turns": c["turns"]} for c in flagged]
        tier2_results = run_analysis(tier2_payload, model)

        # Merge tier2 results into unified output
        for call_id, detailed in tier2_results.items():
            if call_id in results["merged"]:
                results["merged"][call_id] = detailed  # Override with detailed

        results["tier2"] = tier2_results
        logger.info("Tier 2 complete: %d detailed analyses", len(tier2_results))
    else:
        logger.info("Tier 2 skipped: no calls flagged")
        results["tier2"] = {}

    # ── Tier 3: Research Insights ──────────────────────────────────────────────
    if use_tier3 and len(calls) >= 100:  # Minimum sample size
        logger.info("=" * 60)
        logger.info("TIER 3: Research Analysis")
        logger.info("=" * 60)

        try:
            # Prepare data for tier3
            calls_by_hour = _prepare_temporal_data(calls)

            research_results = await run_research_analysis(
                client,
                calls,
                calls_by_hour=calls_by_hour,
                focus=getattr(settings, 'CUSTDEV_PROMPT', None) or ""
            )

            results["tier3"] = research_results
            logger.info("Tier 3 complete: temporal=%s, failures=%s, custdev=%s",
                       bool(research_results.get("temporal")),
                       bool(research_results.get("failure_clusters")),
                       bool(research_results.get("custdev")))

        except Exception as e:
            logger.warning("Tier 3 analysis failed: %s", e)
            results["tier3"] = {"error": str(e)}
    else:
        results["tier3"] = None

    # ── Summary ───────────────────────────────────────────────────────────────
    elapsed = (datetime.now() - start_time).total_seconds()
    results["completed_at"] = datetime.now().isoformat()
    results["elapsed_seconds"] = elapsed

    logger.info("=" * 60)
    logger.info("THREE-TIER ANALYSIS COMPLETE")
    logger.info("=" * 60)
    logger.info("Total time: %.1fs", elapsed)
    logger.info("Tier 1: %d calls screened", len(tier1_results))
    logger.info("Tier 2: %d calls analyzed in detail", len(results.get("tier2", {})))
    logger.info("Tier 3: %s", "complete" if results.get("tier3") else "skipped")

    return results


def _prepare_temporal_data(calls: list[dict]) -> dict:
    """Prepare calls grouped by hour for temporal analysis."""
    from collections import defaultdict

    by_hour = defaultdict(lambda: {
        "count": 0,
        "connected": 0,
        "meetings": 0,
        "total_duration": 0,
        "quality_sum": 0
    })

    for call in calls:
        # Try to extract hour from datetime if available
        dt = call.get("datetime", "")
        hour = "unknown"
        if dt:
            try:
                import pandas as pd
                dt_parsed = pd.to_datetime(dt, errors="coerce")
                if not pd.isna(dt_parsed):
                    hour = int(dt_parsed.hour)
            except Exception:
                pass

        bucket = by_hour[hour]
        bucket["count"] += 1

        outcome = call.get("outcome", "")
        if outcome not in ("no_contact", "contact_only"):
            bucket["connected"] += 1
        if outcome == "meeting":
            bucket["meetings"] += 1

        bucket["total_duration"] += call.get("duration_sec", 0)
        # Use confidence or quality_score if available
        quality = call.get("quality_score", call.get("confidence", 0.5))
        bucket["quality_sum"] += quality

    # Convert to summary dict
    return {
        str(h): {
            "count": data["count"],
            "connect_rate": data["connected"] / data["count"] if data["count"] else 0,
            "meeting_rate": data["meetings"] / data["count"] if data["count"] else 0,
            "avg_duration": data["total_duration"] / data["count"] if data["count"] else 0,
            "avg_quality": data["quality_sum"] / data["count"] if data["count"] else 0
        }
        for h, data in by_hour.items()
    }


# ── Pipeline Integration ─────────────────────────────────────────────────────

def integrate_with_pipeline(
    features: list[dict],
    llm_scope: str = "focus"
) -> tuple[list[dict], dict]:
    """Integration point for build.py pipeline.

    This replaces the LLM section in run_pipeline().

    Args:
        features: List of extracted features from _extract_features
        llm_scope: Scope for analysis ("focus", "full", "sample", "off")

    Returns:
        (features_with_llm, llm_status)
    """
    import asyncio
    from pipeline.config import settings

    llm_status = {
        "configured": settings.llm_configured,
        "provider": settings.primary_provider,
        "scope": llm_scope,
        "mode": "deterministic",
        "calls_analyzed": 0,
        "calls_selected": 0,
        "available": False,
        "note": "",
        "tier1_analyzed": 0,
        "tier2_analyzed": 0,
        "tier3_run": False
    }

    if llm_scope == "off":
        llm_status["note"] = "LLM disabled (scope=off)"
        return features, llm_status

    client = get_client()
    if not client.available:
        llm_status["note"] = "LLM provider unavailable - using deterministic"
        return features, llm_status

    llm_status["available"] = True

    # Prepare calls for analysis
    calls = [
        {
            "id": f"c_{i:05d}",
            "turns": f["turns"],
            "duration_sec": f.get("duration_sec", 0),
            "datetime": f.get("datetime", ""),
            "outcome": f.get("analysis", {}).get("outcome", "")
        }
        for i, f in enumerate(features)
    ]

    # Run three-tier analysis
    try:
        results = asyncio.run(analyze_with_tiers(calls))

        # Update status
        llm_status["mode"] = "llm_tiered"
        llm_status["calls_analyzed"] = len(results.get("merged", {}))
        llm_status["calls_selected"] = len(calls)
        llm_status["tier1_analyzed"] = len(results.get("tier1", {}))
        llm_status["tier2_analyzed"] = len(results.get("tier2", {}))
        llm_status["tier3_run"] = bool(results.get("tier3"))

        # Merge results back into features
        for i, feature in enumerate(features):
            call_id = f"c_{i:05d}"
            if call_id in results.get("merged", {}):
                feature["analysis"] = results["merged"][call_id]

        llm_status["tier3_results"] = results.get("tier3")

    except Exception as e:
        logger.error("Three-tier analysis failed: %s", e)
        llm_status["note"] = f"LLM analysis failed: {str(e)}"
        llm_status["mode"] = "deterministic"

    return features, llm_status
