"""Shared JSON schemas and data contracts for LLM integration.

This module defines:
- Input/output schemas for all three tiers
- Validation functions
- Conversion utilities
- Type definitions

DESIGN PRINCIPLES:
  1. Single source of truth for data contracts
  2. Versioned schemas for backward compatibility
  3. Robust parsing with safe defaults
  4. Clear separation between tiers
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

# ── Schema Version ─────────────────────────────────────────────────────────

CURRENT_SCHEMA_VERSION = "1.0"

# ── Tier 1: Batch Analysis Schema ───────────────────────────────────────────

@dataclass
class BatchCallInput:
    """Input format for batch analysis."""
    id: str
    duration_sec: float
    turns: list[dict]  # [{"role": "bot", "text": "..."}]

    def to_packed(self) -> dict:
        """Convert to packed JSON format for LLM."""
        return {
            "i": self.id,
            "d": self.duration_sec,
            "t": [
                {"r": "b" if t["role"] == "bot" else "c", "txt": t["text"]}
                for t in self.turns
            ]
        }


@dataclass
class BatchAnalysisOutput:
    """Output format from batch analysis."""
    call_id: str
    stage: int  # -1 to 4
    patterns: list[str]  # PSY-* codes
    objections: list[str]  # objection types
    flag: bool  # needs Tier 2 deep dive
    confidence: float  # 0.0 to 1.0
    success: bool = True
    error: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "call_id": self.call_id,
            "stage": self.stage,
            "patterns": self.patterns,
            "objections": self.objections,
            "flag": self.flag,
            "confidence": self.confidence,
            "success": self.success,
            "error": self.error
        }


# ── Tier 2: Detailed Analysis Schema ──────────────────────────────────────────

@dataclass
class DetailedAnalysisOutput:
    """Output format from detailed per-call analysis."""
    call_id: str
    connected: bool
    furthest_stage: int
    stage_evidence: dict  # {"consent": {"reached": bool, "quote": str}, ...}
    outcome: str
    disqualified: bool
    end_attribution: str
    objections: list[dict]  # [{"type": str, "quote": str}, ...]
    bot_patterns: list[dict]  # [{"id": str, "polarity": str, "quote": str}, ...]
    voice: dict  # {"asr_breakdown": bool, "responsiveness": float, ...}
    quality_score: float
    loss_reason: str
    loss_layer: str
    summary: str

    def to_dict(self) -> dict:
        return {
            "source": "llm_tier2",
            "connected": self.connected,
            "furthest_stage": self.furthest_stage,
            "stage_evidence": self.stage_evidence,
            "outcome": self.outcome,
            "disqualified": self.disqualified,
            "end_attribution": self.end_attribution,
            "objections": self.objections,
            "bot_patterns": self.bot_patterns,
            "voice": self.voice,
            "quality_score": self.quality_score,
            "loss_reason": self.loss_reason,
            "loss_layer": self.loss_layer,
            "summary": self.summary
        }

    @classmethod
    def from_unified(cls, data: dict) -> "DetailedAnalysisOutput":
        """Create from unified analysis contract (from analyze.py)."""
        return cls(
            call_id=data.get("call_id", ""),
            connected=data.get("connected", False),
            furthest_stage=data.get("furthest_stage", -1),
            stage_evidence=data.get("stage_evidence", {}),
            outcome=data.get("outcome", "unknown"),
            disqualified=data.get("disqualified", False),
            end_attribution=data.get("end_attribution", ""),
            objections=data.get("objections", []),
            bot_patterns=data.get("bot_patterns", []),
            voice=data.get("voice", {}),
            quality_score=data.get("quality_score", 0.0),
            loss_reason=data.get("loss_reason", ""),
            loss_layer=data.get("loss_layer", ""),
            summary=data.get("summary", "")
        )


# ── Tier 3: Research Analysis Schema ─────────────────────────────────────────

@dataclass
class ResearchOutput:
    """Output format from research analysis."""
    analysis_type: str  # "temporal", "failure_clustering", "conversion_signals", "custdev"
    generated_at: str
    total_calls_analyzed: int
    insights: dict
    success: bool = True
    error: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "type": self.analysis_type,
            "generated_at": self.generated_at,
            "total_calls": self.total_calls_analyzed,
            "insights": self.insights,
            "success": self.success,
            "error": self.error
        }


# ── Threshold Optimization Schema ────────────────────────────────────────────

@dataclass
class ThresholdConfig:
    """Threshold configuration structure."""
    version: int
    last_optimized: Optional[str]
    classification: dict
    quality: dict
    batch_size: dict = field(default_factory=lambda: {"value": 50, "min": 20, "max": 100})

    def to_dict(self) -> dict:
        return {
            "version": self.version,
            "last_optimized": self.last_optimized,
            "classification": self.classification,
            "quality": self.quality,
            "batch_size": self.batch_size
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ThresholdConfig":
        return cls(
            version=data.get("version", 1),
            last_optimized=data.get("last_optimized"),
            classification=data.get("classification", {}),
            quality=data.get("quality", {}),
            batch_size=data.get("batch_size", {"value": 50, "min": 20, "max": 100})
        )


# ── Validation Utilities ─────────────────────────────────────────────────────

def validate_stage(stage: int) -> bool:
    """Validate stage is in expected range."""
    return -1 <= stage <= 4


def validate_confidence(conf: float) -> bool:
    """Validate confidence is in expected range."""
    return 0.0 <= conf <= 1.0


def validate_outcome(outcome: str) -> bool:
    """Validate outcome is one of expected values."""
    valid = {
        "no_contact", "contact_only", "refused", "consent",
        "offer_engaged", "meeting", "qualified"
    }
    return outcome in valid


# ── Conversion Utilities ───────────────────────────────────────────────────────

def batch_to_detailed(
    batch: BatchAnalysisOutput,
    detailed: Optional[DetailedAnalysisOutput]
) -> dict:
    """Merge batch result with detailed analysis if available."""
    base = {
        "call_id": batch.call_id,
        "stage": batch.stage,
        "patterns": batch.patterns,
        "objections": batch.objections,
        "flag": batch.flag,
        "confidence": batch.confidence,
        "source": "llm_tier1"
    }
    if detailed:
        base["detailed"] = detailed.to_dict()
    return base


def unified_from_batch(batch: BatchAnalysisOutput) -> dict:
    """Create unified analysis contract from batch result.

    This allows batch results to feed into metrics.py
    just like detailed analysis results.
    """
    # Map stage to outcome
    stage_to_outcome = {
        -1: "no_contact",
        0: "contact_only",
        1: "consent",
        2: "offer_engaged",
        3: "meeting",
        4: "qualified"
    }

    return {
        "source": "llm_tier1",
        "connected": batch.stage >= 0,
        "furthest_stage": batch.stage,
        "outcome": stage_to_outcome.get(batch.stage, "no_contact"),
        "objections": [{"type": o, "quote": ""} for o in batch.objections],
        "bot_patterns": [{"id": p, "polarity": "negative" if "094" in p or "011" in p else "positive", "quote": ""} for p in batch.patterns],
        "disqualified": False,
        "end_attribution": "",
        "stage_evidence": {
            "consent": {"reached": batch.stage >= 1, "quote": ""},
            "offer_engaged": {"reached": batch.stage >= 2, "quote": ""},
            "meeting_agreed": {"reached": batch.stage >= 3, "quote": ""},
            "qualified": {"reached": batch.stage >= 4, "quote": ""}
        },
        "voice": {
            "asr_breakdown": False,
            "asr_severity": "none",
            "responsiveness": batch.confidence,
            "repair_attempts": 0,
            "bot_talk_share": 0.0,
            "longest_bot_monologue_words": 0
        },
        "quality_score": batch.confidence * 0.8,  # proxy
        "loss_reason": "",
        "loss_layer": "none",
        "summary": ""
    }


# ── Schema Documentation ─────────────────────────────────────────────────────

SCHEMA_DOCS = """
# Botamin BI LLM Integration Schemas

## Version: 1.0

### Tier 1: Batch Analysis

**Input:** List of calls with transcripts
**Output:** Rapid classification (stage, patterns, objections, flag)

**Purpose:** Screen 40-50 calls for key signals
**Latency:** ~3-5 seconds per batch
**Token Efficiency:** ~70% reduction vs per-call

### Tier 2: Detailed Analysis

**Input:** Single call transcript
**Output:** Full analysis with quotes and metrics

**Purpose:** Deep dive on flagged calls only
**Latency:** ~2-3 seconds per call
**Coverage:** ~10-20% of calls (flagged from Tier 1)

### Tier 3: Research Analysis

**Input:** Aggregated statistics + sample transcripts
**Output:** Cross-call patterns and hypotheses

**Purpose:** Discover insights invisible in per-call analysis
**Latency:** ~10-15 seconds per query
**Frequency:** On-demand or scheduled (not per-run)

### Threshold Optimization

**Input:** Current metrics + thresholds
**Output:** Adjustment suggestions with validation

**Purpose:** Auto-tune classification sensitivity
**Frequency:** Weekly or on-demand
"""
