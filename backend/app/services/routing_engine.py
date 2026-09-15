from __future__ import annotations

import logging

from app.models.schemas import ProviderId
from app.services.classification import ClassificationResult

logger = logging.getLogger(__name__)

# Failover order when the chosen provider is unavailable.
FAILOVER_CHAIN: list[ProviderId] = [
    ProviderId.GROQ,
    ProviderId.GEMINI,
    ProviderId.CLOUDFLARE,
    ProviderId.OLLAMA,
]


class RoutingEngine:
    """Pure-Python routing. Considers the FULL classification metadata
    (intent, complexity, reasoning, long-context, code) — not intent alone —
    and executes in well under a millisecond.
    """

    def route(self, result: ClassificationResult) -> ProviderId:
        provider = self._decide(result)
        logger.info(
            "[RoutingEngine] %s/%s (long_ctx=%s, reasoning=%s) → %s",
            result.intent, result.complexity,
            result.requires_long_context, result.requires_reasoning,
            provider.value,
        )
        return provider

    def _decide(self, r: ClassificationResult) -> ProviderId:
        intent, cx = r.intent, r.complexity

        # Coding / debugging: local for trivial, Groq for real code work,
        # Gemini when a large context window is needed.
        if intent in ("coding", "debugging"):
            if cx == "low":
                return ProviderId.OLLAMA
            if cx == "medium":
                return ProviderId.GROQ
            return ProviderId.GEMINI if r.requires_long_context else ProviderId.GROQ

        # Reasoning / math: Gemini's strength; local only for trivial.
        if intent in ("reasoning", "mathematics"):
            return ProviderId.OLLAMA if cx == "low" else ProviderId.GEMINI

        # Education: Gemini for anything beyond a trivial question.
        if intent == "education":
            return ProviderId.OLLAMA if cx == "low" else ProviderId.GEMINI

        # Summarization / document analysis: small stays local, large → Gemini.
        if intent in ("summarization", "document_analysis"):
            if cx == "low" and not r.requires_long_context:
                return ProviderId.OLLAMA
            return ProviderId.GEMINI

        # Translation: short local, long document → Gemini.
        if intent == "translation":
            if cx == "low" and not r.requires_long_context:
                return ProviderId.OLLAMA
            return ProviderId.GEMINI

        # Creative writing: short local, longer pieces → Gemini.
        if intent == "creative_writing":
            return ProviderId.OLLAMA if cx == "low" else ProviderId.GEMINI

        # Research is always heavy.
        if intent == "research":
            return ProviderId.GEMINI

        # Casual conversation stays local unless unusually demanding.
        if intent in ("conversation", "general_chat"):
            return ProviderId.GEMINI if cx == "high" else ProviderId.OLLAMA

        return ProviderId.GEMINI

    def reason(self, result: ClassificationResult, provider: ProviderId) -> str:
        """Human-readable justification, built from the full metadata."""
        intent_label = result.intent.replace("_", " ")
        provider_label = _PROVIDER_LABELS.get(provider, provider.value)

        parts: list[str] = []
        if result.complexity == "high":
            parts.append(f"Large-scale {intent_label} task")
        elif result.complexity == "medium":
            parts.append(f"Moderate {intent_label} task")
        else:
            parts.append(f"Simple {intent_label} task")

        needs: list[str] = []
        if result.requires_code:
            needs.append("strong code generation")
        if result.requires_reasoning:
            needs.append("deep reasoning")
        if result.requires_long_context:
            needs.append("a large context window")
        if needs:
            parts.append("requiring " + _join(needs))

        if provider == ProviderId.OLLAMA:
            parts.append("— handled locally for speed")
        else:
            parts.append(f"— routed to {provider_label}")

        return " ".join(parts) + "."

    def failover_chain(self, primary: ProviderId) -> list[ProviderId]:
        chain = [primary] + [p for p in FAILOVER_CHAIN if p != primary]
        logger.debug("[RoutingEngine] Failover chain: %s", [p.value for p in chain])
        return chain


_PROVIDER_LABELS = {
    ProviderId.GEMINI: "Google Gemini",
    ProviderId.GROQ: "Groq",
    ProviderId.CLOUDFLARE: "Cloudflare Workers AI",
    ProviderId.OLLAMA: "Ollama",
}


def _join(items: list[str]) -> str:
    if len(items) == 1:
        return items[0]
    if len(items) == 2:
        return f"{items[0]} and {items[1]}"
    return ", ".join(items[:-1]) + f", and {items[-1]}"
