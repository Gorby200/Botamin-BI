"""LLM layer for the Botamin BI pipeline.

Three-tier architecture:
  1. Tier 1 (batch.py): Rapid screening of 40-50 calls per request
  2. Tier 2 (analyze.py): Detailed deep dive on flagged calls
  3. Tier 3 (research.py): Aggregated cross-call insights

Supporting modules:
  - client.py: LLM client with retry/fallback
  - schemas.py: Shared data contracts and validation
  - optimizer.py: LLM-driven threshold optimization
  - orchestrator.py: Pipeline integration point

USAGE:
    from pipeline.llm.orchestrator import analyze_with_tiers
    results = await analyze_with_tiers(calls)
"""

from pipeline.llm.client import LLMClient, get_client, LLMResponse
from pipeline.llm.analyze import run_analysis
from pipeline.llm.batch import BatchAnalyzer, BatchResult
from pipeline.llm.research import ResearchAnalyzer, run_research_analysis
from pipeline.llm.optimizer import ThresholdOptimizer, optimize_if_needed
from pipeline.llm.orchestrator import integrate_with_pipeline, _select_for_llm
from pipeline.llm.schemas import (
    BatchAnalysisOutput,
    DetailedAnalysisOutput,
    ResearchOutput,
    ThresholdConfig,
    unified_from_batch
)

__all__ = [
    # Client
    "LLMClient",
    "get_client",
    "LLMResponse",
    # Analysis
    "run_analysis",
    "BatchAnalyzer",
    "BatchResult",
    "ResearchAnalyzer",
    "run_research_analysis",
    # Optimization
    "ThresholdOptimizer",
    "optimize_if_needed",
    # Integration
    "integrate_with_pipeline",
    "_select_for_llm",
    # Schemas
    "BatchAnalysisOutput",
    "DetailedAnalysisOutput",
    "ResearchOutput",
    "ThresholdConfig",
    "unified_from_batch",
]
