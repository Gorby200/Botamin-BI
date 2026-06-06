"""
LLM Client for the Botamin BI pipeline.

ADAPTED from a production dual-provider client (HearAI). What we kept, because it
is the genuinely valuable part, and what we dropped, because it was app-specific:

  KEPT:
    - Dual-provider architecture: Z.ai (GLM, OpenAI-compatible) primary,
      Anthropic Claude fallback.
    - Explicit retry loop with structured error classification (rate_limit / auth /
      bad_request / server / network) so the batch runner can decide intelligently.
    - LLMResponse dataclass for type-safe returns across the codebase.

  DROPPED (was clinical-chatbot specific):
    - Per-state temperature/thinking/max-token tables (SESSION_ACTIVE, SOS, ...).
    - Streaming (a batch pipeline doesn't stream to a user).
    - reasoning_content salvage + STATE_UPDATE envelope parsing.

  ADDED (analysis-specific):
    - complete_json(): forces a JSON object out of the model and parses it robustly
      (strips ```json fences, extracts the outermost {...}).
    - Thinking mode OFF by default — we want fast, deterministic, structured labels.

CALL FLOW:
  1. Try Z.ai with up to LLM_RETRY_COUNT attempts (LLM_RETRY_DELAY_SEC pause).
  2. If all retries fail AND Anthropic key is configured -> fallback to Claude.
  3. If both fail -> return LLMResponse(success=False); the caller falls back to
     the deterministic classifier.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from pipeline.config import settings

logger = logging.getLogger(__name__)


@dataclass
class LLMResponse:
    """Structured response from the LLM (both providers)."""
    content: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: int = 0
    success: bool = True
    error: Optional[str] = None
    provider: str = ""
    error_category: Optional[str] = None
    finish_reason: Optional[str] = None
    cached_tokens: int = 0


class LLMClient:
    """Dual-provider LLM client with retry + fallback, for batch analysis.

    USAGE:
        from pipeline.llm.client import get_client
        client = get_client()
        resp = await client.complete_json(system=..., user_message=...)
        if resp.success:
            data = resp.parsed   # dict, already JSON-parsed
    """

    def __init__(self) -> None:
        self._zhipu_client = None
        self._anthropic_client = None

        # Lazily construct provider SDK clients. Guarded so the module imports
        # even when the SDKs aren't installed (pure-deterministic environments).
        if settings.ZHIPU_API_KEY:
            try:
                from openai import AsyncOpenAI

                self._zhipu_client = AsyncOpenAI(
                    api_key=settings.ZHIPU_API_KEY,
                    base_url=settings.ZHIPU_BASE_URL,
                    max_retries=0,  # we handle retries ourselves
                    timeout=settings.LLM_TIMEOUT_SEC,
                )
            except Exception as e:  # pragma: no cover
                logger.warning("openai SDK unavailable, Z.ai disabled: %s", e)

        if settings.ANTHROPIC_API_KEY:
            try:
                import anthropic

                self._anthropic_client = anthropic.AsyncAnthropic(
                    api_key=settings.ANTHROPIC_API_KEY,
                    timeout=settings.LLM_TIMEOUT_SEC,
                )
            except Exception as e:  # pragma: no cover
                logger.warning("anthropic SDK unavailable, fallback disabled: %s", e)

    # ── Health ─────────────────────────────────────────────────────────────
    @property
    def available(self) -> bool:
        return self._zhipu_client is not None or self._anthropic_client is not None

    @property
    def active_provider(self) -> str:
        if self._zhipu_client is not None:
            return "zhipu"
        if self._anthropic_client is not None:
            return "anthropic"
        return "none"

    # ── Public API ───────────────────────────────────────────────────────────
    async def complete(
        self,
        system: str,
        user_message: str,
        model: str = "",
        temperature: float | None = None,
        max_tokens: int | None = None,
        thinking: bool = False,
    ) -> LLMResponse:
        """Single completion with retry + fallback. Returns LLMResponse."""
        temperature = settings.LLM_TEMPERATURE if temperature is None else temperature
        max_tokens = settings.LLM_MAX_TOKENS if max_tokens is None else max_tokens
        messages = [{"role": "user", "content": user_message}]

        # ── Primary: Z.ai with retries ──────────────────────────────────────
        if self._zhipu_client is not None:
            zmodel = model or settings.LLM_PRIMARY_MODEL
            for attempt in range(1, settings.LLM_RETRY_COUNT + 1):
                start = time.monotonic()
                resp = await self._call_zhipu(
                    zmodel, system, messages, temperature, max_tokens, thinking
                )
                resp.latency_ms = int((time.monotonic() - start) * 1000)
                if resp.success:
                    return resp
                logger.warning(
                    "Z.ai attempt %d/%d failed [%s]: %s",
                    attempt, settings.LLM_RETRY_COUNT,
                    resp.error_category, (resp.error or "")[:160],
                )
                # bad_request won't be fixed by retry or by Anthropic with same payload
                if resp.error_category == "bad_request":
                    return resp
                # auth -> go straight to fallback (can't fix with retry)
                if resp.error_category == "auth":
                    break
                # rate_limit -> retry with exponential backoff
                if resp.error_category == "rate_limit":
                    if attempt < settings.LLM_RETRY_COUNT:
                        backoff = min(settings.LLM_RETRY_DELAY_SEC * (2 ** (attempt - 1)), 30)
                        logger.info("Rate limit hit, retrying in %.1fs...", backoff)
                        await asyncio.sleep(backoff)
                        continue
                    else:
                        logger.warning("Rate limit persisted after %d retries, falling back", attempt)
                # other errors -> standard retry delay
                if attempt < settings.LLM_RETRY_COUNT and resp.error_category != "rate_limit":
                    await asyncio.sleep(settings.LLM_RETRY_DELAY_SEC)

        # ── Fallback: Anthropic ─────────────────────────────────────────────
        if self._anthropic_client is not None:
            start = time.monotonic()
            resp = await self._call_anthropic(system, messages, temperature, max_tokens, model)
            resp.latency_ms = int((time.monotonic() - start) * 1000)
            return resp

        return LLMResponse(
            content="", model="none", success=False,
            error="No LLM provider configured", provider="none",
            error_category="all_failed",
        )

    async def complete_json(
        self,
        system: str,
        user_message: str,
        model: str = "",
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        """Like complete(), but instructs the model to return a JSON object and
        attaches the parsed dict to `resp.parsed` (None if parsing fails)."""
        system_json = (
            system
            + "\n\nВЕРНИ ТОЛЬКО валидный JSON-объект без markdown-обёртки, "
            "без пояснений до или после. Все ключи и значения — строго по схеме."
        )
        resp = await self.complete(system_json, user_message, model, temperature, max_tokens)
        parsed = None
        if resp.success and resp.content:
            parsed = _extract_json(resp.content)
            if parsed is None:
                resp.success = False
                resp.error_category = "parse_error"
                resp.error = "Could not parse JSON from model output"
        # attach dynamically (dataclass without slots allows this)
        resp.parsed = parsed  # type: ignore[attr-defined]
        return resp

    # ── Provider implementations ─────────────────────────────────────────────
    async def _call_zhipu(
        self, model, system, messages, temperature, max_tokens, thinking
    ) -> LLMResponse:
        try:
            extra_body = {"thinking": {"type": "enabled" if thinking else "disabled"}}
            response = await self._zhipu_client.chat.completions.create(
                model=model,
                messages=[{"role": "system", "content": system}, *messages],
                temperature=temperature,
                max_tokens=max_tokens,
                extra_body=extra_body,
            )
            if not response.choices:
                return LLMResponse(
                    content="", model=model, success=False,
                    error="Empty choices", provider="zhipu", error_category="server",
                )
            msg = response.choices[0].message
            content = msg.content or ""
            usage = response.usage
            return LLMResponse(
                content=content,
                model=model,
                input_tokens=getattr(usage, "prompt_tokens", 0) if usage else 0,
                output_tokens=getattr(usage, "completion_tokens", 0) if usage else 0,
                success=bool(content),
                provider="zhipu",
                finish_reason=response.choices[0].finish_reason,
                error=None if content else "empty content",
                error_category=None if content else "server",
            )
        except Exception as e:
            return _classify_openai_error(e, model)

    async def _call_anthropic(
        self, system, messages, temperature, max_tokens, model
    ) -> LLMResponse:
        amodel = model or settings.LLM_FALLBACK_MODEL
        anthropic_max = min(max_tokens, 8192)
        try:
            response = await self._anthropic_client.messages.create(
                model=amodel,
                system=system,
                messages=messages,
                temperature=temperature,
                max_tokens=anthropic_max,
            )
            content = response.content[0].text if response.content else ""
            return LLMResponse(
                content=content,
                model=amodel,
                input_tokens=response.usage.input_tokens,
                output_tokens=response.usage.output_tokens,
                success=bool(content),
                provider="anthropic",
                finish_reason=response.stop_reason,
            )
        except Exception as e:
            logger.error("Anthropic error: %s", e)
            err = str(e).lower()
            cat = "unknown"
            if "rate" in err or "429" in err:
                cat = "rate_limit"
            elif "auth" in err or "401" in err or "403" in err:
                cat = "auth"
            elif "timeout" in err or "connection" in err:
                cat = "network"
            return LLMResponse(
                content="", model=amodel, success=False, error=str(e),
                provider="anthropic", error_category=cat,
            )


def _extract_json(text: str) -> Optional[dict]:
    """Robustly extract a JSON object from a model response.

    Models occasionally wrap JSON in ```json fences or add a stray sentence.
    We strip fences, then take the outermost {...} block and json.loads it.
    """
    if not text:
        return None
    t = text.strip()
    # strip code fences
    t = re.sub(r"^```(?:json)?\s*", "", t)
    t = re.sub(r"\s*```$", "", t)
    # direct parse first
    try:
        return json.loads(t)
    except Exception:
        pass
    # outermost brace block
    start = t.find("{")
    end = t.rfind("}")
    if start >= 0 and end > start:
        try:
            return json.loads(t[start : end + 1])
        except Exception:
            return None
    return None


def _classify_openai_error(exc: Exception, model: str) -> LLMResponse:
    """Map openai SDK exceptions to a structured LLMResponse."""
    try:
        from openai import (
            RateLimitError, AuthenticationError, BadRequestError,
            APIConnectionError, APIStatusError,
        )
    except Exception:  # pragma: no cover
        return LLMResponse(content="", model=model, success=False, error=str(exc),
                            provider="zhipu", error_category="unknown")

    if isinstance(exc, RateLimitError):
        cat = "rate_limit"
    elif isinstance(exc, AuthenticationError):
        cat = "auth"
    elif isinstance(exc, BadRequestError):
        cat = "bad_request"
    elif isinstance(exc, APIConnectionError):
        cat = "network"
    elif isinstance(exc, APIStatusError):
        status = getattr(exc, "status_code", 0)
        cat = "server" if status >= 500 else "bad_request"
    else:
        cat = "unknown"
    return LLMResponse(content="", model=model, success=False, error=str(exc),
                       provider="zhipu", error_category=cat)


# Singleton accessor (lazy — built on first use so importing this module is cheap)
_client: Optional[LLMClient] = None


def get_client() -> LLMClient:
    global _client
    if _client is None:
        _client = LLMClient()
    return _client
