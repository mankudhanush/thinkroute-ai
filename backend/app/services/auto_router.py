from __future__ import annotations

import logging
import time
import traceback
from datetime import datetime

from app.errors import AppError
from app.models.schemas import AutoChatRequest, AutoChatResponse, ProviderId, RoutingMetadata
from app.providers.base_provider import ChatTurn
from app.services.classification import ClassificationResult
from app.services.hybrid_classifier import HybridClassifier
from app.services.memory.context_packet_builder import ContextPacket
from app.services.memory.memory_engine import MemoryEngine
from app.services.model_selector import ModelSelector
from app.services.provider_factory import ProviderFactory
from app.services.provider_service import ProviderService
from app.services.routing_engine import RoutingEngine
from app.services.storage_service import StorageService

logger = logging.getLogger(__name__)


class AutoRouter:
    """Orchestrates Auto Mode:

        prompt → hybrid classify → route (metadata) → select model → provider

    The classifier NEVER answers the prompt; the selected provider always
    generates the final response. Every stage is timed and the totals are
    returned to the UI.
    """

    def __init__(
        self,
        storage: StorageService,
        providers: ProviderService,
        classifier: HybridClassifier,
        routing_engine: RoutingEngine,
        model_selector: ModelSelector,
        memory: MemoryEngine,
    ) -> None:
        self.storage = storage
        self.providers = providers
        self.classifier = classifier
        self.routing_engine = routing_engine
        self.model_selector = model_selector
        self.memory = memory

    async def route_and_chat(self, request: AutoChatRequest) -> AutoChatResponse:
        sep = "=" * 50
        t_total = time.perf_counter()
        logger.info("\n%s\nAUTO MODE\n%s\nPrompt: %.200s", sep, sep, request.message)

        # ── Stage 1: Hybrid classification (rules first, LLM if uncertain) ──
        classification, classification_ms = await self.classifier.classify(request.message)
        logger.info(
            "Intent: %s | Complexity: %s | Confidence: %.0f%% | via: %s",
            classification.intent, classification.complexity,
            classification.confidence * 100, classification.source,
        )

        # ── Stage 2: Routing (pure Python) ─────────────────────────────────
        t_route = time.perf_counter()
        primary = self.routing_engine.route(classification)
        reason = self.routing_engine.reason(classification, primary)
        failover_chain = self.routing_engine.failover_chain(primary)
        routing_ms = (time.perf_counter() - t_route) * 1000
        logger.info("Provider: %s | Reason: %s | Routing: %.2fms", primary.value, reason, routing_ms)

        # ── Stage 3: Context-Aware Memory (provider-independent, computed once) ──
        history = self.storage.history(request.conversation_id)
        packet, engine_ms = self.memory.build_context(request.conversation_id, request.message, history)
        logger.info(
            "Context: thread=%s | %d/%d msgs sent | %.2fms",
            packet.thread_id, packet.used_count, packet.total_history, engine_ms,
        )

        # ── Stage 4: Send ORIGINAL prompt to the provider (with failover) ──
        last_error: Exception | None = None
        for provider_id in failover_chain:
            record = self.storage.get_provider(provider_id)
            if not record or not record["connected"]:
                logger.debug("[AutoRouter] '%s' not connected, skipping", provider_id.value)
                continue

            model_id = self.model_selector.select(provider_id)
            if not model_id:
                logger.debug("[AutoRouter] No models for '%s', skipping", provider_id.value)
                continue

            if provider_id != primary:
                logger.info("Failover → Provider: %s | Model: %s", provider_id.value, model_id)
            else:
                logger.info("Model: %s", model_id)

            try:
                t_provider = time.perf_counter()
                response_text = await self._send_original_prompt(request, provider_id, model_id, packet)
                provider_ms = (time.perf_counter() - t_provider) * 1000
                total_ms = (time.perf_counter() - t_total) * 1000

                logger.info(
                    "%s\nAUTO MODE SUCCESS — provider=%s | model=%s | "
                    "classify=%.0fms route=%.2fms context=%.2fms provider=%.0fms total=%.0fms\n%s",
                    sep, provider_id.value, model_id,
                    classification_ms, routing_ms, engine_ms, provider_ms, total_ms, sep,
                )

                routing = self._build_metadata(
                    classification, reason, provider_id,
                    classification_ms, routing_ms, provider_ms, total_ms,
                )
                # Persist the turn only on success (user first, then assistant).
                self.storage.save_message(
                    request.conversation_id, "user", request.message, provider_id, model_id,
                    thread_id=packet.thread_id, keywords=self.memory.keywords_csv(request.message),
                )
                created_at = self.storage.save_message(
                    request.conversation_id, "assistant", response_text, provider_id, model_id,
                    thread_id=packet.thread_id,
                )
                return AutoChatResponse(
                    conversation_id=request.conversation_id,
                    provider=provider_id,
                    model=model_id,
                    response=response_text,
                    created_at=datetime.fromisoformat(created_at),
                    routing=routing,
                    context=self.memory.to_context_info(packet, engine_ms),
                )
            except Exception as exc:
                last_error = exc
                logger.warning(
                    "[AutoRouter] FAILOVER — '%s' failed: %s. Trying next...",
                    provider_id.value, str(exc)[:200],
                )
                continue

        error_msg = (
            f"All providers failed. Last error: {last_error}"
            if last_error else "No connected providers available"
        )
        logger.error("AUTO MODE FAILED — %s", error_msg)
        raise AppError(error_msg, 503, "provider_offline")

    def _build_metadata(
        self,
        c: ClassificationResult,
        reason: str,
        provider: ProviderId,
        classification_ms: float,
        routing_ms: float,
        provider_ms: float,
        total_ms: float,
    ) -> RoutingMetadata:
        return RoutingMetadata(
            intent=c.intent,
            complexity=c.complexity,
            confidence=c.confidence,
            estimated_output=c.estimated_output,
            requires_reasoning=c.requires_reasoning,
            requires_code=c.requires_code,
            requires_long_context=c.requires_long_context,
            offline_possible=c.offline_possible,
            reason=reason,
            classified_by=c.source,
            classification_ms=round(classification_ms, 2),
            routing_ms=round(routing_ms, 3),
            provider_ms=round(provider_ms, 2),
            total_ms=round(total_ms, 2),
        )

    async def _send_original_prompt(
        self,
        request: AutoChatRequest,
        provider_id: ProviderId,
        model_id: str,
        packet: ContextPacket,
    ) -> str:
        """Send the ORIGINAL user prompt (plus the memory engine's selected
        context, NOT the full history) to the selected provider/model.

        The intent classifier already ran and is NOT involved here — this is
        the provider the routing engine chose generating the real answer.
        The user turn is persisted by the caller only on success, so a
        failover retry never double-saves it.
        """
        messages = packet.to_chat_turns()
        credentials = self.providers.credentials(provider_id)
        adapter = ProviderFactory.create(provider_id, credentials)
        try:
            return await adapter.chat(model_id, messages)
        except Exception:
            logger.error(
                "[AutoRouter] Chat failed: provider=%s model=%s\n%s",
                provider_id.value, model_id, traceback.format_exc(),
            )
            raise
