"""Configuration for the Botamin BI pipeline.

Centralises every tunable knob and secret in one place, loaded from a `.env`
file at the project root (see `.env.example`). The analyst/operator pastes their
own API keys and base URL — nothing is hard-coded.

WHY A CONFIG MODULE (and not os.getenv scattered everywhere):
  - The LLM client (pipeline/llm/client.py) was lifted from another project where
    it imported `app.config.settings`. We keep the same `settings` interface so the
    client adapts with minimal edits.
  - One source of truth for "is the LLM available?" — the whole pipeline degrades
    gracefully to the deterministic failsafe when no key is configured.

LLM SCOPE (the "depth of analysis" switch the PO asked for):
  focus  — run the LLM only on substantive dialogues (>= MIN_CLIENT_TURNS client
           turns). ~850-2000 calls. Cheap, fast, accurate where it matters.
  full   — run the LLM on every connected conversation (~8 400). Thorough, 4-5x cost.
  sample — run on a random sample (LLM_SAMPLE_SIZE) for calibration; the rest stay
           deterministic. Used to estimate LLM-vs-heuristic agreement.
  off    — never call the LLM. Pure deterministic failsafe.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

# Load .env from project root if python-dotenv is available.
# Absence of dotenv is non-fatal: env vars may be set by the shell instead.
try:
    from dotenv import load_dotenv

    _ROOT = Path(__file__).resolve().parent.parent
    load_dotenv(_ROOT / ".env")
except Exception:  # pragma: no cover - dotenv is optional
    pass


def _get(key: str, default: str = "") -> str:
    return os.environ.get(key, default).strip()


def _get_int(key: str, default: int) -> int:
    try:
        return int(os.environ.get(key, str(default)))
    except (ValueError, TypeError):
        return default


def _get_float(key: str, default: float) -> float:
    try:
        return float(os.environ.get(key, str(default)))
    except (ValueError, TypeError):
        return default


@dataclass
class Settings:
    # ─── Provider credentials (paste in .env) ──────────────────────────────
    # Primary: Z.ai / Zhipu GLM via the OpenAI-compatible SDK.
    ZHIPU_API_KEY: str = field(default_factory=lambda: _get("ZHIPU_API_KEY"))
    ZHIPU_BASE_URL: str = field(
        default_factory=lambda: _get("ZHIPU_BASE_URL", "https://api.z.ai/api/paas/v4/")
    )
    # Fallback: Anthropic Claude.
    ANTHROPIC_API_KEY: str = field(default_factory=lambda: _get("ANTHROPIC_API_KEY"))

    # ─── Model selection ───────────────────────────────────────────────────
    LLM_PRIMARY_MODEL: str = field(
        default_factory=lambda: _get("LLM_PRIMARY_MODEL", "glm-4.6")
    )
    LLM_FALLBACK_MODEL: str = field(
        default_factory=lambda: _get("LLM_FALLBACK_MODEL", "claude-sonnet-4-5")
    )

    # ─── Retry / fallback behaviour ────────────────────────────────────────
    LLM_RETRY_COUNT: int = field(default_factory=lambda: _get_int("LLM_RETRY_COUNT", 2))
    LLM_RETRY_DELAY_SEC: float = field(
        default_factory=lambda: _get_float("LLM_RETRY_DELAY_SEC", 3.0)
    )
    LLM_TIMEOUT_SEC: float = field(
        default_factory=lambda: _get_float("LLM_TIMEOUT_SEC", 120.0)
    )

    # ─── Batch behaviour (analysis-specific, not in the original client) ────
    # How many calls to analyse concurrently. Keep modest to respect rate limits.
    LLM_CONCURRENCY: int = field(default_factory=lambda: _get_int("LLM_CONCURRENCY", 6))
    # Default scope when --llm-scope is not passed on the CLI.
    LLM_SCOPE: str = field(default_factory=lambda: _get("LLM_SCOPE", "focus"))
    # A dialogue needs at least this many CLIENT turns to qualify as "substantive"
    # and thus be sent to the LLM under the 'focus' scope.
    MIN_CLIENT_TURNS: int = field(default_factory=lambda: _get_int("MIN_CLIENT_TURNS", 3))
    # Random sample size when scope == 'sample'.
    LLM_SAMPLE_SIZE: int = field(default_factory=lambda: _get_int("LLM_SAMPLE_SIZE", 1000))
    # Temperature for the analysis task: low — we want consistent, structured labels.
    LLM_TEMPERATURE: float = field(
        default_factory=lambda: _get_float("LLM_TEMPERATURE", 0.2)
    )
    LLM_MAX_TOKENS: int = field(default_factory=lambda: _get_int("LLM_MAX_TOKENS", 4096))

    # CustDev research lens (empty -> built-in default in custdev.py).
    CUSTDEV_PROMPT: str = field(default_factory=lambda: _get("CUSTDEV_PROMPT"))

    # ─── Three-tier LLM configuration ─────────────────────────────────────────
    # Batch size for Tier 1 rapid screening
    # Optimized for GLM-5.1 200K context: ~180 substantive calls per batch
    # Calculation: 150K available tokens / ~263 tokens per substantive call = ~570
    # Conservative 180 for reliability, processing time, and output limits
    LLM_BATCH_SIZE: int = field(default_factory=lambda: _get_int("LLM_BATCH_SIZE", 180))
    # Enable Tier 3 research analysis
    LLM_ENABLE_RESEARCH: bool = field(default_factory=lambda: _get("LLM_ENABLE_RESEARCH", "true").lower() == "true")
    # Minimum calls for Tier 3 analysis
    LLM_MIN_RESEARCH_SAMPLE: int = field(default_factory=lambda: _get_int("LLM_MIN_RESEARCH_SAMPLE", 100))
    # Enable automatic threshold optimization
    LLM_AUTO_OPTIMIZE: bool = field(default_factory=lambda: _get("LLM_AUTO_OPTIMIZE", "false").lower() == "true")

    @property
    def llm_configured(self) -> bool:
        """True if at least one provider key is present."""
        return bool(self.ZHIPU_API_KEY or self.ANTHROPIC_API_KEY)

    @property
    def primary_provider(self) -> str:
        if self.ZHIPU_API_KEY:
            return "zhipu"
        if self.ANTHROPIC_API_KEY:
            return "anthropic"
        return "none"


settings = Settings()
