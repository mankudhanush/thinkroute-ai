from __future__ import annotations

import logging
import time

from app.services.classification import ClassificationResult
from app.services.intent_classifier import IntentClassifier
from app.services.rule_classifier import RuleClassifier

logger = logging.getLogger(__name__)

# Rule confidence at/above this skips the LLM entirely.
CONFIDENCE_THRESHOLD = 0.85


class HybridClassifier:
    """Two-tier classifier optimised for latency.

    1. A deterministic rule classifier runs first (<1 ms). For obvious prompts
       ("build a website", "translate this", "hello") it returns high
       confidence and the qwen3:4b intent model is never touched.
    2. Only when the rules are uncertain do we fall back to the intent model.

    Returns the :class:`ClassificationResult` plus the elapsed classification
    time in milliseconds so the router can report per-stage timing.
    """

    def __init__(self, rules: RuleClassifier, model: IntentClassifier) -> None:
        self.rules = rules
        self.model = model

    async def classify(self, prompt: str) -> tuple[ClassificationResult, float]:
        start = time.perf_counter()

        rule_result = self.rules.classify(prompt)
        if rule_result.confidence >= CONFIDENCE_THRESHOLD:
            elapsed_ms = (time.perf_counter() - start) * 1000
            logger.info(
                "[Hybrid] rule-path %s/%s conf=%.2f in %.1fms (LLM skipped)",
                rule_result.intent, rule_result.complexity,
                rule_result.confidence, elapsed_ms,
            )
            return rule_result, elapsed_ms

        logger.info(
            "[Hybrid] rule confidence %.2f < %.2f → invoking intent model",
            rule_result.confidence, CONFIDENCE_THRESHOLD,
        )
        model_result = await self.model.classify(prompt)
        elapsed_ms = (time.perf_counter() - start) * 1000
        logger.info(
            "[Hybrid] model-path %s/%s conf=%.2f in %.1fms",
            model_result.intent, model_result.complexity,
            model_result.confidence, elapsed_ms,
        )
        return model_result, elapsed_ms
