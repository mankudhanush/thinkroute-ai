"""LLM gateway for one-shot completions (used by the editor).

Editing needs the raw model output (an edit plan) WITHOUT writing to
conversation history, so it can't go through the chat-persisting ``AutoRouter``.
This gateway still REUSES the existing pieces — provider credentials + adapters
(``ProviderFactory``) for the call, and the existing ``RoutingEngine`` +
classifier + ``ModelSelector`` for provider choice — so no routing logic is
duplicated. All collaborators are injected.
"""

from __future__ import annotations

import logging

from app.models.schemas import ProviderId
from app.providers.base_provider import ChatTurn
from app.services.repository.exceptions import RepositoryError

logger = logging.getLogger(__name__)


class LlmGatewayError(RepositoryError):
    status_code = 502
    code = "llm_gateway_error"


class NoProviderAvailableError(LlmGatewayError):
    status_code = 503
    code = "no_provider_available"


class LlmGateway:
    def __init__(
        self,
        provider_service,
        storage_service,
        classifier,
        routing_engine,
        model_selector,
    ) -> None:
        self._providers = provider_service
        self._storage = storage_service
        self._classifier = classifier
        self._routing = routing_engine
        self._model_selector = model_selector

    async def complete(
        self,
        messages: list[ChatTurn],
        *,
        routing_hint: str,
        provider: str | None = None,
        model: str | None = None,
    ) -> tuple[str, str, str]:
        """Return (text, provider, model). Uses the caller's provider/model when
        given, otherwise reuses the routing engine to choose (with failover)."""
        if provider:
            return await self._complete_with(provider, model, messages)
        return await self._complete_auto(messages, routing_hint)

    # -- explicit provider --------------------------------------------------

    async def _complete_with(
        self, provider: str, model: str | None, messages: list[ChatTurn]
    ) -> tuple[str, str, str]:
        try:
            provider_id = ProviderId(provider)
        except ValueError as exc:
            raise LlmGatewayError(f"Unknown provider '{provider}'.") from exc
        resolved_model = model or self._model_selector.select(provider_id)
        if not resolved_model:
            raise LlmGatewayError(f"No model available for provider '{provider}'.")
        text = await self._invoke(provider_id, resolved_model, messages)
        return text, provider_id.value, resolved_model

    # -- routed selection (reuses RoutingEngine + classifier) ---------------

    async def _complete_auto(
        self, messages: list[ChatTurn], routing_hint: str
    ) -> tuple[str, str, str]:
        classification, _ = await self._classifier.classify(routing_hint)
        primary = self._routing.route(classification)
        chain = self._routing.failover_chain(primary)

        last_error: Exception | None = None
        for provider_id in chain:
            record = self._storage.get_provider(provider_id)
            if not record or not record["connected"]:
                continue
            model = self._model_selector.select(provider_id)
            if not model:
                continue
            try:
                text = await self._invoke(provider_id, model, messages)
                return text, provider_id.value, model
            except Exception as exc:  # failover to the next provider
                last_error = exc
                logger.warning("[LlmGateway] %s failed: %s — trying next", provider_id.value, str(exc)[:200])
        if last_error:
            raise NoProviderAvailableError(f"All providers failed. Last error: {last_error}")
        raise NoProviderAvailableError("No connected provider with an available model.")

    # -- provider call ------------------------------------------------------

    async def _invoke(self, provider_id: ProviderId, model: str, messages: list[ChatTurn]) -> str:
        from app.services.provider_factory import ProviderFactory

        credentials = self._providers.credentials(provider_id)
        adapter = ProviderFactory.create(provider_id, credentials)
        logger.info("[LlmGateway] completing via %s/%s", provider_id.value, model)
        return await adapter.chat(model, messages)
