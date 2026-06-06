"""Research LLM analyzer for aggregated cross-call insights.

This module implements Tier 3 of the three-tier LLM strategy:
- Temporal pattern analysis
- Failure mode clustering
- Conversion signal discovery
- CustDev theme extraction

DESIGN PRINCIPLES:
  1. Input is aggregated statistics, not raw transcripts (token efficient)
  2. Focus on cross-call patterns invisible in per-call analysis
  3. Generate actionable hypotheses for product and prompt improvement
  4. Separate from operational analysis — runs on-demand or scheduled

USAGE:
    from pipeline.llm.research import ResearchAnalyzer
    analyzer = ResearchAnalyzer(get_client())
    insights = await analyzer.temporal_analysis(calls_by_hour)
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Optional

from pipeline.llm.client import LLMClient

logger = logging.getLogger(__name__)

# ── Research Prompts ────────────────────────────────────────────────────────

TEMPORAL_ANALYSIS_PROMPT = """
Ты — продуктовый аналитик голосового AI-агента продаж.

ДАННЫЕ (агрегированные метрики по часам, посчитаны пайплайном — НЕ выдумывай свои числа):
{data}

ВАЖНО: в полях metrics указывай ТОЛЬКО значения из предоставленных данных. Не сочиняй
проценты и лифты, которых нет во входных данных. Выводы — это гипотезы, формулируй осторожно.

ЗАДАЧА:
Найди временные паттерны в качестве диалогов и в конверсии.

АНАЛИЗ:
1. Какие часы/дни показывают аномально высокие или низкие результаты?
2. Есть ли корреляция между временем звонка и:
   - Длительностью разговора
   - Долей успешных встреч
   - Частотой возражений
   - Качеством связи (ASR failures)

Верни JSON:
{{
  "patterns": [
    {{
      "time_window": "9:00-11:00 понедельник",
      "characteristics": "Клиенты более открыты, меньше отказов",
      "metrics": {{
        "connect_rate": 0.65,
        "meeting_rate": 0.12,
        "quality_score": 0.68
      }},
      "difference_from_avg": "connect_rate на +15%, meeting_rate на +40%",
      "hypothesis": "Утром понедельника клиенты более мотивированы",
      "recommendation": "Усилить обзвон в это окно"
    }}
  ],
  "warnings": [
    {{
      "time_window": "17:00-18:00 пятница",
      "issue": "Высокий процент instant_hangup",
      "possible_cause": "Усталость к концу недели"
    }}
  ],
  "overall_insights": "..."
}}
"""

FAILURE_CLUSTERING_PROMPT = """
Ты — эксперт по анализу отказов в продажах.

ДАННЫЕ (выборка неудачных звонков):
{data}

ВАЖНО: цитаты бери ТОЛЬКО из предоставленных расшифровок (дословно). Поля size_estimate и
pct_of_failed — это ПРИБЛИЗИТЕЛЬНЫЕ оценки по выборке (гипотезы), а не точные измерения;
оценивай консервативно и не выдавай выдуманные точные числа за факт.

ЗАДАЧА:
Сгруппируй неудачные звонки в кластеры по причине потери клиента.

КЛАСТЕРЫ МОГУТ ВКЛЮЧАТЬ:
- Weak opener (не получил согласие)
- Boring pitch (оффер не зацепил)
- Objection unhandled (возражение не отработано)
- No close (не предложили встречу)
- ASR breakdown (проблемы связи)
- Disqualified (бот сам отказался)

Для каждого кластера:
1. Описать типичный профиль звонка
2. Привести 2-3 характерные цитаты
3. Предложить гипотезу для улучшения

Верни JSON:
{{
  "clusters": [
    {{
      "name": "Weak Opener - No Consent",
      "size_estimate": 450,
      "pct_of_failed": 0.23,
      "characteristics": "Клиент отвечает 1-2 словами, не задаёт вопросов",
      "typical_quotes": [
        "Алло? Да. Не интересно. [кладёт трубку]",
        "Слушаю. Да-да-да. Не надо. Всё."
      ],
      "stage_where_lost": "S0→S1",
      "hypothesis": "Опенер слишком длинный или не даёт ценность сразу",
      "prompt_fix_suggestion": "Сократить опенер, добавить конкретную выгоду в первые 2 реплики"
    }}
  ],
  "priority_order": ["Weak Opener", "Objection Unhandled", "No Close"],
  "quick_wins": ["Suggested fix for highest-impact cluster"]
}}
"""

CONVERSION_SIGNALS_PROMPT = """
Ты — data scientist, специализирующийся на предиктивной аналитике для продаж.

ДАННЫЕ (выборка звонков):
{data}

ВАЖНО: значения lift/correlation — это КАЧЕСТВЕННЫЕ гипотезы по выборке (направление и
сила сигнала), а не точно измеренные коэффициенты. Не выдавай выдуманные точные числа за
факт; если уверенности нет — описывай словами (strong/medium/weak).

ЗАДАЧА:
Найди сигналы, которые предсказывают успешную встречу.

МОДЕЛИРУЕМЫЕ СИГНАЛЫ:
- Длительность разговора
- Количество substantive реплик клиента
- Наличие вопросов по продукту
- Отсутствие ценовых возражений
- Позитивные паттерны бота (PSY-010, PSY-047)
- Отсутствие отрицательных паттернов

Верни JSON:
{{
  "strong_signals": [
    {{
      "signal": "Клиент задаёт вопросы по продукту",
      "correlation": "strong",
      "lift": "2.8x conversion rate",
      "explanation": "Вопросы = интерес = готовность к встрече"
    }}
  ],
  "negative_predictors": [
    {{
      "signal": "Ценовое возражение в первые 30 секунд",
      "correlation": "negative",
      "lift": "0.3x conversion rate",
      "explanation": "Ранний вопрос о цене = хладнокровное сравнение"
    }}
  ],
  "surprising_findings": "Неочевидные корреляции",
  "scoring_model": {{
    "weights": {{"client_questions": 0.4, "duration_over_60s": 0.2, ...}},
    "threshold": 0.65
  }}
}}
"""

CUSTDEV_EXTRACTION_PROMPT = """
Ты — CustDev исследователь (Voice of Customer).

ДАННЫЕ:
{data}

ФОКУС ИССЛЕДОВАНИЯ:
{focus}

ЗАДАЧА:
Извлеки из разговоров инсайты о клиентах:
- Боли и проблемы
- Пожелания к продукту
- Конкуренты и альтернативы
- Чувствительность к цене
- Процесс принятия решения
- Доверие к ИИ

Верни JSON:
{{
  "insights": [
    {{
      "category": "pain",
      "theme": "Текучка лидов из-за ручного обзвона",
      "quotes": [
        "У нас менеджеры разгребают incoming, а на холодный не хватает рук",
        "Сами звоним, но быстро устают, много текучки"
      ],
      "frequency": "упоминается в 8% звонков",
      "recommendation": "Усилить pain на 'автоматизация рутинных звонков'"
    }}
  ],
  "new_hypotheses": [
    {{
      "hypothesis": "Клиенты с B2B-сегментом более ценят экономию времени менеджеров",
      "validation_method": "A/B тест с акцентом на time-to-lead vs cost-per-lead"
    }}
  ]
}}
"""


class ResearchAnalyzer:
    """Cross-call pattern discovery and aggregated analysis.

    USAGE:
        analyzer = ResearchAnalyzer(client)
        temporal = await analyzer.temporal_analysis(calls_by_hour)
        failures = await analyzer.failure_clustering(failed_calls)
        signals = await analyzer.conversion_signals(all_calls)
    """

    def __init__(self, client: LLMClient):
        self.client = client

    def _prepare_summary_stats(self, data: list[dict] | dict) -> str:
        """Convert data to summary statistics for LLM input.

        Focus on aggregated stats, not raw transcripts.
        """
        if isinstance(data, dict):
            return json.dumps(data, ensure_ascii=False, default=str)
        if isinstance(data, list):
            # Create summary
            if len(data) > 100:
                # Deterministic sample (fixed seed) so re-runs over the same data
                # produce the same insights — reproducibility matters for validation.
                import random
                sample = random.Random(1234).sample(data, 100)
                return f"Sample of {len(data)} items:\n{json.dumps(sample, ensure_ascii=False, default=str)}"
            return json.dumps(data, ensure_ascii=False, default=str)
        return str(data)

    async def temporal_analysis(
        self,
        calls_by_hour: dict | list,
        model: str = ""
    ) -> Optional[dict]:
        """Analyze temporal patterns in call outcomes.

        Args:
            calls_by_hour: Data grouped by hour/day
            model: Optional model override

        Returns:
            Dict with patterns, warnings, insights
        """
        if not self.client.available:
            logger.warning("LLM unavailable for temporal analysis")
            return None

        data_str = self._prepare_summary_stats(calls_by_hour)

        try:
            resp = await self.client.complete_json(
                system=TEMPORAL_ANALYSIS_PROMPT.format(data=data_str),
                user_message="Проанализируй временные паттерны",
                model=model,
            )

            if resp.success and resp.parsed:
                return resp.parsed
            return None

        except Exception as e:
            logger.error("Temporal analysis failed: %s", e)
            return None

    async def failure_clustering(
        self,
        failed_calls: list[dict] | dict,
        model: str = ""
    ) -> Optional[dict]:
        """Cluster failed calls into distinct failure modes.

        Args:
            failed_calls: Failed call data with outcomes

        Returns:
            Dict with clusters, hypotheses, priorities
        """
        if not self.client.available:
            logger.warning("LLM unavailable for failure clustering")
            return None

        data_str = self._prepare_summary_stats(failed_calls)

        try:
            resp = await self.client.complete_json(
                system=FAILURE_CLUSTERING_PROMPT.format(data=data_str),
                user_message="Сгруппируй отказы в кластеры",
                model=model,
            )

            if resp.success and resp.parsed:
                return resp.parsed
            return None

        except Exception as e:
            logger.error("Failure clustering failed: %s", e)
            return None

    async def conversion_signals(
        self,
        all_calls: list[dict] | dict,
        model: str = ""
    ) -> Optional[dict]:
        """Identify signals that predict successful conversion.

        Args:
            all_calls: All call data with outcomes

        Returns:
            Dict with strong_signals, negative_predictors, scoring_model
        """
        if not self.client.available:
            logger.warning("LLM unavailable for conversion signals")
            return None

        data_str = self._prepare_summary_stats(all_calls)

        try:
            resp = await self.client.complete_json(
                system=CONVERSION_SIGNALS_PROMPT.format(data=data_str),
                user_message="Найди сигналы конверсии",
                model=model,
            )

            if resp.success and resp.parsed:
                return resp.parsed
            return None

        except Exception as e:
            logger.error("Conversion signals analysis failed: %s", e)
            return None

    async def custdev_extraction(
        self,
        calls_with_transcripts: list[dict],
        focus: str = "",
        model: str = ""
    ) -> Optional[dict]:
        """Extract customer development insights from transcripts.

        Args:
            calls_with_transcripts: Calls with transcript text
            focus: Optional research lens override

        Returns:
            Dict with insights, hypotheses, themes
        """
        if not self.client.available:
            logger.warning("LLM unavailable for CustDev extraction")
            return None

        # Limit to avoid token blowout. Deterministic sample for reproducibility.
        sample_size = min(200, len(calls_with_transcripts))
        import random
        sampled = (random.Random(1234).sample(calls_with_transcripts, sample_size)
                   if sample_size < len(calls_with_transcripts) else calls_with_transcripts)

        data_str = self._prepare_summary_stats(sampled)

        try:
            resp = await self.client.complete_json(
                system=CUSTDEV_EXTRACTION_PROMPT.format(
                    data=data_str,
                    focus=focus or "боли и задачи клиента, пожелания, возражения, конкуренты"
                ),
                user_message="Извлеки CustDev инсайты",
                model=model,
            )

            if resp.success and resp.parsed:
                return resp.parsed
            return None

        except Exception as e:
            logger.error("CustDev extraction failed: %s", e)
            return None


# ── Aggregated Research Runner ───────────────────────────────────────────────

async def run_research_analysis(
    client: LLMClient,
    calls: list[dict],
    calls_by_hour: Optional[dict] = None,
    focus: str = ""
) -> dict:
    """Run full research analysis suite.

    Args:
        client: LLM client
        calls: All call data
        calls_by_hour: Optional temporal grouping
        focus: Optional CustDev focus

    Returns:
        Dict with all research outputs
    """
    analyzer = ResearchAnalyzer(client)

    results = {
        "generated_at": datetime.now().isoformat(),
        "total_calls_analyzed": len(calls),
        "temporal": None,
        "failure_clusters": None,
        "conversion_signals": None,
        # CustDev is produced by the dedicated GROUNDED map-reduce path
        # (pipeline/custdev.py) — per-call extraction with verbatim quotes and
        # pipeline-computed counts. We deliberately do NOT run the aggregate,
        # number-fabricating CustDev here; it is kept only for ad-hoc analysis.
        "custdev": None,
    }

    # Temporal analysis
    if calls_by_hour:
        logger.info("Running temporal analysis...")
        results["temporal"] = await analyzer.temporal_analysis(calls_by_hour)

    # Failure clustering (filter failed calls)
    failed = [c for c in calls if c.get("outcome") in ["refused", "contact_only", "consent"]]
    if failed:
        logger.info("Running failure clustering (%d calls)...", len(failed))
        results["failure_clusters"] = await analyzer.failure_clustering(failed)

    # Conversion signals
    logger.info("Running conversion signals analysis...")
    results["conversion_signals"] = await analyzer.conversion_signals(calls)

    return results
