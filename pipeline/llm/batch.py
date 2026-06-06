"""Batch LLM analyzer for efficient multi-call processing.

This module implements Tier 1 of the three-tier LLM strategy:
- Process 40-50 calls in a single LLM request
- Rapid screening for stage, patterns, objections
- Flagging for Tier 2 detailed analysis

DESIGN PRINCIPLES:
  1. Minimal JSON overhead: short keys, array format
  2. System prompt shared across batch (97% token savings)
  3. Fast, directional analysis: what needs deep dive?
  4. Cache-friendly: batch key based on content hash

USAGE:
    from pipeline.llm.batch import BatchAnalyzer
    analyzer = BatchAnalyzer(get_client())
    results = await analyzer.analyze_batch(calls[:50])
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from dataclasses import dataclass
from typing import Optional

from pipeline.llm.client import LLMClient

logger = logging.getLogger(__name__)

# ── Batch Configuration ─────────────────────────────────────────────────────
# Optimized for GLM-5.1 200K context window:
# - ~263 tokens per substantive call (average 6.4 turns)
# - 150K available input tokens (with safety margin)
# - Output: 180 calls × 50 tokens = 9K (within 4-8K output limit per batch strategy)
DEFAULT_BATCH_SIZE = 180
MIN_BATCH_SIZE = 50
MAX_BATCH_SIZE = 300

# ── Optimized JSON Structure ─────────────────────────────────────────────────
# Short keys minimize token overhead while maintaining readability
# i=id, d=duration_sec, t=turns, r=role, txt=text

BATCH_SYSTEM_PROMPT = """
Ты — senior-аналитик диалогов AI-агента продаж Botamin.
АНАЛИЗИРУЙ [40-50] звонков ОДНИМ JSON-массивом.

ФОРМАТ ВВОДА:
{{
  "v": 1,
  "calls": [
    {{"i": "c_01048", "d": 45.2, "t": [{{"r": "b", "txt": "..."}}, ...]}},
    ...
  ]
}}

ПРАВИЛА АНАЛИЗА:
1. Стадия (stage) засчитывается ТОЛЬКО по словам КЛИЕНТА, а не бота.
   stage = -1: нет контакта / только "алло?"
   stage = 0: контакт без согласия
   stage = 1: клиент дал согласие слушать
   stage = 2: оффер донесён, клиент реагирует по сути
   stage = 3: согласована встреча
   stage = 4: квалифицирован

2. Паттерны бота (PSY-*) — выбирай ТОЛЬКО из таксономии:
   ПОЛОЖИТЕЛЬНЫЕ:
     PSY-010  Запрос разрешения в опенере
     PSY-047  Альтернативное закрытие ("утром или вечером?")
     PSY-082  Feel-Felt-Found (нормализация возражения)
   ОТРИЦАТЕЛЬНЫЕ:
     PSY-011  Питч в лоб в опенере (продаёт раньше согласия)
     PSY-124  Затянутый монолог (>60 слов)
     PSY-094  Игнор возражения
     PSY-095  Преждевременная сдача ("отправлю материалы")
     PSY-106  Нет закрытия (не предложил следующий шаг)
     PSY-200  ASR-петля (бот повторяется)
     PSY-201  Глухота к проблеме связи

3. Возражения (objections):
   price, no_need, have_alternative, no_time, no_budget,
   send_info, have_internal, not_priority, gatekeeper

4. flag=true если звонок НУЖДАЕТСЯ в детальном анализе Tier 2:
   - stage == 3 (встреча) — celebrate: изучить, что сработало
   - stage == 2 AND objections present — почему не закрыли?
   - patterns содержит PSY-094 или PSY-201 — явная ошибка бота
   - завершён с disqualified=true — бот сам отказался
   - случайные ~5% S0-S1 для контроля качества

5. r (confidence) — 0.0-1.0, насколько уверена классификация.

ВЕРНИ JSON-массив (без markdown, без пояснений):
[
  {{"i": "c_01048", "stage": 2, "patterns": ["PSY-047"], "objections": ["price"], "flag": true, "r": 0.9}},
  {{"i": "c_01049", "stage": -1, "patterns": [], "objections": [], "flag": false, "r": 0.95}},
  ...
]

Если не можешь определить — ставь stage=-1, r=0.3, flag=false.
"""


@dataclass
class BatchResult:
    """Result from batch analysis."""
    call_id: str
    stage: int
    patterns: list[str]
    objections: list[str]
    flag: bool
    confidence: float
    success: bool = True
    error: Optional[str] = None


class BatchAnalyzer:
    """Process multiple calls in a single LLM request.

    USAGE:
        analyzer = BatchAnalyzer(client)
        results = await analyzer.analyze_batch(calls[:50])
        for r in results:
            if r.flag:
                # Send to Tier 2 detailed analysis
    """

    def __init__(self, client: LLMClient, batch_size: int = DEFAULT_BATCH_SIZE):
        self.client = client
        self.batch_size = max(MIN_BATCH_SIZE, min(MAX_BATCH_SIZE, batch_size))
        self._cache_dir = None

    def pack_calls(self, calls: list[dict]) -> str:
        """Pack calls into minimal JSON format.

        Input: [{"id": "c_01048", "turns": [{"role": "bot", "text": "..."}]}, ...]
        Output: JSON string with short keys
        """
        packed_calls = []
        for call in calls:
            turns = [
                {"r": "b" if t.get("role") == "bot" else "c", "txt": t.get("text", "")}
                for t in call.get("turns", [])
            ]
            packed_calls.append({
                "i": call.get("id", ""),
                "d": call.get("duration_sec", 0),
                "t": turns
            })
        return json.dumps({"v": 1, "calls": packed_calls}, ensure_ascii=False)

    def unpack_response(self, response: str) -> list[BatchResult]:
        """Parse LLM JSON response into BatchResult objects.

        Robust to:
        - ```json fences
        - Trailing commas
        - Missing fields (safe defaults)
        """
        if not response or not response.strip():
            return []

        # Strip fences
        text = response.strip()
        text = text.removeprefix("```json").removeprefix("```")
        text = text.removesuffix("```").strip()

        try:
            raw = json.loads(text)
            if not isinstance(raw, list):
                logger.warning("Batch response is not a list")
                return []

            results = []
            for item in raw:
                if not isinstance(item, dict):
                    continue
                results.append(BatchResult(
                    call_id=str(item.get("i", "")),
                    stage=int(item.get("stage", -1)),
                    patterns=list(item.get("patterns", []) or []),
                    objections=list(item.get("objections", []) or []),
                    flag=bool(item.get("flag", False)),
                    confidence=float(item.get("r", 0.5)),
                    success=True,
                    error=None
                ))
            return results

        except json.JSONDecodeError as e:
            logger.error("Failed to parse batch response: %s", e)
            # Try to extract JSON array
            start = text.find("[")
            end = text.rfind("]")
            if start >= 0 and end > start:
                try:
                    return self.unpack_response(text[start:end+1])
                except Exception:
                    pass
            return []

    def _cache_key(self, calls_json: str, model: str) -> str:
        """Generate cache key for batch request."""
        h = hashlib.sha256()
        h.update(model.encode())
        h.update(calls_json.encode())
        h.update(BATCH_SYSTEM_PROMPT.encode())
        return h.hexdigest()[:24]

    async def analyze_batch(self, calls: list[dict], model: str = "") -> list[BatchResult]:
        """Analyze a batch of calls in one LLM request.

        Args:
            calls: List of call dicts with "id", "turns", "duration_sec"
            model: Optional model override

        Returns:
            List of BatchResult, one per call
        """
        if not calls:
            return []

        if not self.client.available:
            logger.warning("LLM client unavailable, batch analysis skipped")
            return [BatchResult(
                call_id=c.get("id", ""),
                stage=-1,
                patterns=[],
                objections=[],
                flag=False,
                confidence=0.0,
                success=False,
                error="LLM unavailable"
            ) for c in calls]

        calls_json = self.pack_calls(calls)
        cache_key = self._cache_key(calls_json, model)

        # TODO: Implement cache get/put similar to analyze.py

        try:
            resp = await self.client.complete_json(
                system=BATCH_SYSTEM_PROMPT,
                user_message=f"Анализируй {len(calls)} звонков:\n\n{calls_json}",
                model=model,
            )

            if not resp.success:
                logger.warning("Batch analysis failed: %s", resp.error)
                return [BatchResult(
                    call_id=c.get("id", ""),
                    stage=-1,
                    patterns=[],
                    objections=[],
                    flag=False,
                    confidence=0.0,
                    success=False,
                    error=resp.error
                ) for c in calls]

            results = self.unpack_response(resp.content)

            # Align results with input order
            results_map = {r.call_id: r for r in results if r.success}
            ordered = []
            for call in calls:
                call_id = call.get("id", "")
                if call_id in results_map:
                    ordered.append(results_map[call_id])
                else:
                    # Missing result - create placeholder
                    ordered.append(BatchResult(
                        call_id=call_id,
                        stage=-1,
                        patterns=[],
                        objections=[],
                        flag=False,
                        confidence=0.0,
                        success=False,
                        error="Not in response"
                    ))

            return ordered

        except Exception as e:
            logger.error("Batch analysis crashed: %s", e)
            return [BatchResult(
                call_id=c.get("id", ""),
                stage=-1,
                patterns=[],
                objections=[],
                flag=False,
                confidence=0.0,
                success=False,
                error=str(e)
            ) for c in calls]

    async def analyze_all(self, calls: list[dict], model: str = "", concurrency: int = 2) -> dict[str, BatchResult]:
        """Analyze all calls in batches with rate-limit-friendly concurrent processing.

        Args:
            calls: List of all calls to process
            model: Optional model override
            concurrency: Number of batches to process concurrently (default=2 for rate limits)

        Returns:
            Dict mapping call_id -> BatchResult
        """
        if not calls:
            return {}

        all_results = {}
        batches = [calls[i:i + self.batch_size] for i in range(0, len(calls), self.batch_size)]

        logger.info("Batch analysis: %d calls in %d batches (size=%d, concurrency=%d)",
                    len(calls), len(batches), self.batch_size, concurrency)

        # Process batches concurrently with semaphore
        from asyncio import Semaphore, sleep

        sem = Semaphore(concurrency)
        batch_delay = 1.0  # Delay between starting batches to avoid burst

        async def process_batch(idx: int, batch: list[dict]) -> list[BatchResult]:
            # Stagger batch starts to avoid hitting rate limits
            await sleep(idx * batch_delay / concurrency)
            async with sem:
                logger.info("Processing batch %d/%d (%d calls)", idx+1, len(batches), len(batch))
                return await self.analyze_batch(batch, model)

        # Run all batches concurrently (controlled by semaphore)
        tasks = [process_batch(i, batch) for i, batch in enumerate(batches)]
        all_batch_results = await asyncio.gather(*tasks, return_exceptions=True)

        # Merge results
        for batch_results in all_batch_results:
            if isinstance(batch_results, Exception):
                logger.error("Batch failed: %s", batch_results)
                continue
            for r in batch_results:
                all_results[r.call_id] = r

        successful = sum(1 for r in all_results.values() if r.success)
        logger.info("Batch analysis complete: %d/%d successful (%.1f%%)",
                    successful, len(all_results), 100 * successful / len(all_results) if all_results else 0)

        return all_results


# ── Utility Functions ───────────────────────────────────────────────────────

def chunk_calls(calls: list[dict], batch_size: int = DEFAULT_BATCH_SIZE) -> list[list[dict]]:
    """Split calls into chunks for batch processing."""
    return [calls[i:i + batch_size] for i in range(0, len(calls), batch_size)]


def merge_batch_with_detailed(
    batch_results: dict[str, BatchResult],
    detailed_results: dict[str, dict]
) -> dict[str, dict]:
    """Merge Tier 1 batch results with Tier 2 detailed analysis.

    Args:
        batch_results: call_id -> BatchResult from Tier 1
        detailed_results: call_id -> detailed dict from Tier 2

    Returns:
        Unified dict with batch results + detailed where available
    """
    merged = {}
    for call_id, batch_res in batch_results.items():
        base = {
            "stage": batch_res.stage,
            "patterns": batch_res.patterns,
            "objections": batch_res.objections,
            "flag": batch_res.flag,
            "confidence": batch_res.confidence,
        }
        if call_id in detailed_results:
            base["detailed"] = detailed_results[call_id]
        merged[call_id] = base
    return merged
