"""LLM-driven threshold optimizer for Botamin BI.

This module implements dynamic threshold optimization using LLM feedback:
- Analyze current metrics and threshold performance
- Suggest adjustments to improve precision/recall
- Validate proposals before applying
- Maintain threshold history and rollback capability

DESIGN PRINCIPLES:
  1. Human-in-the-loop: LLM suggests, human approves
  2. Safe defaults: can rollback to previous working values
  3. Metric-driven: suggestions based on actual performance
  4. A/B testing framework: validate changes before full rollout

USAGE:
    from pipeline.llm.optimizer import ThresholdOptimizer
    optimizer = ThresholdOptimizer(get_client())
    suggestions = await optimizer.suggest_adjustments(current_metrics)
    validated = await optimizer.validate_proposal(suggestions)
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

from pipeline.llm.client import LLMClient

logger = logging.getLogger(__name__)

# ── Configuration Paths ─────────────────────────────────────────────────────
THRESHOLDS_PATH = Path("config/thresholds.yaml")
HISTORY_PATH = Path("config/thresholds_history.json")

# ── Optimizer Prompts ────────────────────────────────────────────────────────

OPTIMIZER_SYSTEM_PROMPT = """
Ты — expert по машинному обучению и продуктовой аналитике.
Твоя специализация — настройка порогов классификации для максимизации
полезности метрик при сохранении надежности.

КОНТЕКСТ:
Мы анализируем голосовые звонки AI-агента продаж. У нас есть детерминированный
классификатор с настраиваемыми порогами. Наша цель — баланс между:

1. PRECISION — минимизировать ложные срабатывания (шум)
2. RECALL — поймать все реальные проблемы (пропуски)
3. STABILITY — избежать частых изменений

ТЕКУЩАЯ СИТУАЦИЯ:
{current_situation}

ЦЕЛЬ:
Предложи корректировки threshold'ов для улучшения метрик.

ВАЖНЫЕ ПРИНЦИПЫ:
- Изменяй по одному параметру за раз
- Обосновывай каждое изменение метриками
- Предупреждай о рисках
- Предлагай валидацию

Верни JSON:
{{
  "analysis": {{
    "current_performance": "Оценка текущей конфигурации",
    "identified_issues": ["что не так сейчас"],
    "improvement_opportunities": ["что можно улучшить"]
  }},
  "suggestions": [
    {{
      "threshold": "min_client_turns",
      "current_value": 3,
      "suggested_value": 4,
      "expected_impact": "Увеличит precision на 5%, незначительно снизит recall",
      "risk_level": "low",
      "risk_description": "Можем пропустить некоторые короткие но содержательные диалоги",
      "validation_method": "Сравнить classification на выборке 100 звонков",
      "rollback_condition": "Если precision < 0.85"
    }}
  ],
  "priority_order": ["какие изменения попробовать первыми"],
  "overall_recommendation": "Суммарная рекомендация"
}}
"""

VALIDATION_PROMPT = """
Ты — QA-инженер, проверяющий предложения по изменению конфигурации.

ПРЕДЛОЖЕНИЕ:
{proposal}

ТЕКУЩИЕ МЕТРИКИ:
{metrics}

ЗАДАЧА:
Оцени, безопасно ли применять это изменение.

ПРОВЕРКИ:
1. Логически ли значение (не выходят ли за разумные пределы)?
2. Есть ли риск негативного влияния на ключевые метрики?
3. Нужна ли дополнительная валидация?

Верни JSON:
{{
  "safe": true/false,
  "concerns": ["проблемы если есть"],
  "additional_checks_needed": ["что ещё проверить"],
  "recommendation": "apply|reject|validate_first",
  "validation_plan": "если validate_first — что сделать"
}}
"""


@dataclass
class ThresholdSuggestion:
    """A single threshold adjustment suggestion."""
    threshold: str
    current_value: float | int
    suggested_value: float | int
    expected_impact: str
    risk_level: str
    risk_description: str
    validation_method: str
    rollback_condition: str


@dataclass
class OptimizationProposal:
    """Complete optimization proposal from LLM."""
    analysis: dict
    suggestions: list[ThresholdSuggestion]
    priority_order: list[str]
    overall_recommendation: str
    generated_at: str


class ThresholdOptimizer:
    """LLM-driven threshold optimization with human-in-the-loop validation.

    USAGE:
        optimizer = ThresholdOptimizer(client)
        proposal = await optimizer.suggest_adjustments(metrics)
        validated = await optimizer.validate_proposal(proposal, metrics)
        if validated["safe"]:
            optimizer.apply_threshold(proposal.suggestions[0])
    """

    def __init__(self, client: LLMClient, thresholds_path: Path = THRESHOLDS_PATH):
        self.client = client
        self.thresholds_path = thresholds_path
        self.history_path = HISTORY_PATH

    def load_current_thresholds(self) -> dict:
        """Load current threshold configuration."""
        if self.thresholds_path.exists():
            try:
                import yaml
                with open(self.thresholds_path, encoding="utf-8") as f:
                    return yaml.safe_load(f)
            except Exception as e:
                logger.warning("Failed to load thresholds: %s", e)

        # Return defaults
        return {
            "version": 1,
            "last_optimized": None,
            "classification": {
                "min_client_turns": {"value": 3, "min": 2, "max": 5},
                "substantive_word_count": {"value": 2, "min": 1, "max": 4},
            },
            "quality": {
                "warning_threshold": {"value": 0.4, "min": 0.2, "max": 0.6},
            },
        }

    def save_thresholds(self, thresholds: dict) -> None:
        """Save threshold configuration and archive previous version."""
        # Archive current version
        current = self.load_current_thresholds()
        self._archive_to_history(current)

        # Save new version
        try:
            import yaml
            self.thresholds_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.thresholds_path, "w", encoding="utf-8") as f:
                yaml.dump(thresholds, f, allow_unicode=True, default_flow_style=False)
            logger.info("Saved thresholds to %s", self.thresholds_path)
        except Exception as e:
            logger.error("Failed to save thresholds: %s", e)

    def _archive_to_history(self, thresholds: dict) -> None:
        """Archive current thresholds to history."""
        self.history_path.parent.mkdir(parents=True, exist_ok=True)

        history = []
        if self.history_path.exists():
            try:
                history = json.loads(self.history_path.read_text(encoding="utf-8"))
            except Exception:
                pass

        thresholds["archived_at"] = datetime.now().isoformat()
        history.insert(0, thresholds)

        # Keep only last 20 versions
        history = history[:20]

        self.history_path.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")

    def _prepare_situation_description(
        self,
        metrics: dict,
        thresholds: Optional[dict] = None
    ) -> str:
        """Prepare situation description for LLM."""
        thresholds = thresholds or self.load_current_thresholds()

        return f"""
ТЕКУЩИЕ ПОРОГИ:
```json
{json.dumps(thresholds, ensure_ascii=False, indent=2)}
```

ТЕКУЩИЕ МЕТРИКИ:
```json
{json.dumps(metrics, ensure_ascii=False, indent=2)}
```

ПРОБЛЕМА (если есть):
Если есть конкретная проблема с текущей конфигурацией, опиши её здесь.
"""

    async def suggest_adjustments(
        self,
        metrics: dict,
        problem: str = "",
        model: str = ""
    ) -> Optional[OptimizationProposal]:
        """Generate threshold adjustment suggestions using LLM.

        Args:
            metrics: Current performance metrics
            problem: Optional specific problem description
            model: Optional model override

        Returns:
            OptimizationProposal with suggestions
        """
        if not self.client.available:
            logger.warning("LLM unavailable for optimization")
            return None

        thresholds = self.load_current_thresholds()
        situation = self._prepare_situation_description(metrics, thresholds)

        if problem:
            situation += f"\nПРОБЛЕМА: {problem}"

        try:
            resp = await self.client.complete_json(
                system=OPTIMIZER_SYSTEM_PROMPT.format(current_situation=situation),
                user_message="Предложи корректировки threshold'ов",
                model=model,
            )

            if not resp.success or not resp.parsed:
                logger.warning("Optimization suggestion failed: %s", resp.error)
                return None

            parsed = resp.parsed

            # Convert to structured objects
            suggestions = []
            for s in parsed.get("suggestions", []):
                suggestions.append(ThresholdSuggestion(
                    threshold=str(s.get("threshold", "")),
                    current_value=s.get("current_value", 0),
                    suggested_value=s.get("suggested_value", 0),
                    expected_impact=str(s.get("expected_impact", "")),
                    risk_level=str(s.get("risk_level", "unknown")),
                    risk_description=str(s.get("risk_description", "")),
                    validation_method=str(s.get("validation_method", "")),
                    rollback_condition=str(s.get("rollback_condition", "")),
                ))

            return OptimizationProposal(
                analysis=parsed.get("analysis", {}),
                suggestions=suggestions,
                priority_order=parsed.get("priority_order", []),
                overall_recommendation=parsed.get("overall_recommendation", ""),
                generated_at=datetime.now().isoformat(),
            )

        except Exception as e:
            logger.error("Optimization suggestion crashed: %s", e)
            return None

    async def validate_proposal(
        self,
        proposal: OptimizationProposal,
        current_metrics: dict,
        model: str = ""
    ) -> dict:
        """Validate an optimization proposal before applying.

        Args:
            proposal: The proposal to validate
            current_metrics: Current metrics for comparison
            model: Optional model override

        Returns:
            Dict with safe, concerns, recommendation
        """
        if not self.client.available:
            return {"safe": False, "recommendation": "reject", "concerns": ["LLM unavailable"]}

        proposal_str = json.dumps({
            "analysis": proposal.analysis,
            "suggestions": [
                {
                    "threshold": s.threshold,
                    "from": s.current_value,
                    "to": s.suggested_value,
                    "impact": s.expected_impact,
                    "risk": s.risk_level
                }
                for s in proposal.suggestions
            ],
            "recommendation": proposal.overall_recommendation
        }, ensure_ascii=False, indent=2)

        metrics_str = json.dumps(current_metrics, ensure_ascii=False, indent=2)

        try:
            resp = await self.client.complete_json(
                system=VALIDATION_PROMPT.format(
                    proposal=proposal_str,
                    metrics=metrics_str
                ),
                user_message="Проверь предложение на безопасность",
                model=model,
            )

            if resp.success and resp.parsed:
                return resp.parsed

            return {"safe": False, "recommendation": "reject", "concerns": ["Validation failed"]}

        except Exception as e:
            logger.error("Validation failed: %s", e)
            return {"safe": False, "recommendation": "reject", "concerns": [str(e)]}

    def apply_threshold(self, suggestion: ThresholdSuggestion) -> bool:
        """Apply a single threshold adjustment.

        Args:
            suggestion: The suggestion to apply

        Returns:
            True if applied successfully
        """
        thresholds = self.load_current_thresholds()

        # Navigate to the threshold
        # This is a simplified implementation - in production,
        # you'd want more robust path handling
        parts = suggestion.threshold.split(".")
        target = thresholds
        for part in parts[:-1]:
            if part not in target:
                target[part] = {}
            target = target[part]

        # Update value
        key = parts[-1]
        if isinstance(target.get(key), dict):
            target[key]["value"] = suggestion.suggested_value
            target[key]["llm_suggested"] = suggestion.suggested_value
            target[key]["rationale"] = suggestion.expected_impact
        else:
            target[key] = suggestion.suggested_value

        thresholds["version"] += 1
        thresholds["last_optimized"] = datetime.now().isoformat()

        self.save_thresholds(thresholds)
        return True

    def rollback(self, versions_back: int = 1) -> bool:
        """Rollback to a previous threshold configuration.

        Args:
            versions_back: How many versions to go back

        Returns:
            True if rollback successful
        """
        if not self.history_path.exists():
            logger.warning("No history to rollback to")
            return False

        try:
            history = json.loads(self.history_path.read_text(encoding="utf-8"))

            if versions_back >= len(history):
                logger.warning("Cannot rollback %d versions (only %d available)", versions_back, len(history))
                return False

            target = history[versions_back]
            target["restored_from"] = f"version {versions_back} back"
            target["restored_at"] = datetime.now().isoformat()

            self.save_thresholds(target)
            logger.info("Rolled back to version from %s", target.get("archived_at"))
            return True

        except Exception as e:
            logger.error("Rollback failed: %s", e)
            return False


# ── Convenience Functions ───────────────────────────────────────────────────

async def optimize_if_needed(
    client: LLMClient,
    metrics: dict,
    problem: str = "",
    auto_apply_safe: bool = False
) -> dict:
    """Run optimization cycle and optionally apply safe changes.

    Args:
        client: LLM client
        metrics: Current metrics
        problem: Optional specific problem
        auto_apply_safe: If True, applies low-risk suggestions automatically

    Returns:
        Dict with proposal, validation, and applied changes
    """
    optimizer = ThresholdOptimizer(client)

    # Get suggestions
    proposal = await optimizer.suggest_adjustments(metrics, problem)
    if not proposal:
        return {"status": "failed", "reason": "Could not generate proposal"}

    # Validate
    validation = await optimizer.validate_proposal(proposal, metrics)

    result = {
        "proposal": proposal,
        "validation": validation,
        "applied": []
    }

    # Apply safe suggestions if requested
    if auto_apply_safe and validation.get("safe"):
        for suggestion in proposal.suggestions:
            if suggestion.risk_level == "low":
                if optimizer.apply_threshold(suggestion):
                    result["applied"].append(suggestion.threshold)

    result["status"] = "applied" if result["applied"] else "review_required"
    return result
