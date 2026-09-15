from __future__ import annotations

from dataclasses import dataclass, replace

# ---------------------------------------------------------------------------
# Shared vocabulary
# ---------------------------------------------------------------------------
VALID_INTENTS = frozenset({
    "coding", "debugging", "reasoning", "education", "mathematics",
    "summarization", "translation", "creative_writing",
    "document_analysis", "research", "conversation", "general_chat",
})
VALID_COMPLEXITIES = frozenset({"low", "medium", "high"})
VALID_OUTPUTS = frozenset({"small", "medium", "large"})

# Intents whose primary deliverable is source code.
_CODE_INTENTS = frozenset({"coding", "debugging"})
# Intents that are inherently reasoning-heavy regardless of complexity.
_REASONING_INTENTS = frozenset({"reasoning", "mathematics", "research"})
# Intents that typically ingest a large source document.
_LONG_SOURCE_INTENTS = frozenset({"summarization", "document_analysis", "research"})


@dataclass(frozen=True)
class ClassificationResult:
    """The unified output of the classification stage.

    Both the fast rule-based classifier and the qwen3:4b intent model produce
    the three *core* fields (intent, complexity, confidence). Everything else
    is derived deterministically by :func:`enrich` so the two paths always
    yield consistent metadata and the LLM can stay fast with a tiny schema.
    """

    intent: str
    complexity: str
    confidence: float
    estimated_output: str = "medium"
    requires_reasoning: bool = False
    requires_code: bool = False
    requires_long_context: bool = False
    offline_possible: bool = True
    reason: str = ""
    source: str = "rule"  # "rule" | "model" | "fallback"

    @staticmethod
    def fallback() -> "ClassificationResult":
        return enrich("general_chat", "medium", 0.0, source="fallback")


def _normalize(intent: str, complexity: str) -> tuple[str, str]:
    intent = (intent or "").lower().strip()
    complexity = (complexity or "").lower().strip()
    if intent not in VALID_INTENTS:
        intent = "general_chat"
    if complexity not in VALID_COMPLEXITIES:
        complexity = "medium"
    return intent, complexity


def _estimated_output(intent: str, complexity: str) -> str:
    # Output size reflects the size of the *response*, not the prompt.
    # Summarization/translation condense or mirror their input, so their
    # output stays modest even for high-complexity (large) sources.
    if intent == "summarization":
        return "small" if complexity == "low" else "medium"
    if intent == "translation":
        return "small" if complexity == "low" else "medium"
    if complexity == "high":
        return "large"
    if complexity == "low":
        return "small"
    return "medium"


def enrich(
    intent: str,
    complexity: str,
    confidence: float,
    *,
    source: str = "rule",
) -> ClassificationResult:
    """Derive the full semantic metadata from the three core fields.

    Centralising this keeps the rule path and the model path perfectly
    consistent and lets the intent model return only three tokens' worth of
    JSON (fast) while the API still exposes the rich contract.
    """
    intent, complexity = _normalize(intent, complexity)
    confidence = max(0.0, min(1.0, float(confidence)))

    estimated_output = _estimated_output(intent, complexity)
    requires_code = intent in _CODE_INTENTS
    requires_reasoning = (
        complexity == "high"
        or intent in _REASONING_INTENTS
    )
    requires_long_context = (
        estimated_output == "large"
        or (intent in _LONG_SOURCE_INTENTS and complexity in ("medium", "high"))
    )
    # A task is offline-friendly only when it is small and self-contained.
    offline_possible = complexity == "low" and not requires_long_context

    return ClassificationResult(
        intent=intent,
        complexity=complexity,
        confidence=confidence,
        estimated_output=estimated_output,
        requires_reasoning=requires_reasoning,
        requires_code=requires_code,
        requires_long_context=requires_long_context,
        offline_possible=offline_possible,
        source=source,
    )


def with_reason(result: ClassificationResult, reason: str) -> ClassificationResult:
    return replace(result, reason=reason)
