from __future__ import annotations

import logging
import traceback
from datetime import datetime

from app.errors import AppError
from app.models.schemas import ChatRequest, ChatResponse, HistoryMessage
from app.providers.base_provider import ChatTurn
from app.services.memory.memory_engine import MemoryEngine
from app.services.model_service import ModelService
from app.services.provider_factory import ProviderFactory
from app.services.provider_service import ProviderService
from app.services.storage_service import StorageService

logger = logging.getLogger(__name__)


class ChatService:
    def __init__(
        self,
        storage: StorageService,
        providers: ProviderService,
        models: ModelService,
        memory: MemoryEngine,
    ) -> None:
        self.storage = storage
        self.providers = providers
        self.models = models
        self.memory = memory

    async def chat(self, request: ChatRequest) -> ChatResponse:
        logger.info(
            "=== CHAT REQUEST === provider=%s | model=%s | conversation=%s",
            request.provider.value, request.model, request.conversation_id,
        )

        # Validate model belongs to the requested provider
        self.models.ensure_available(request.provider, request.model)
        logger.debug("Model '%s' validated for provider '%s'", request.model, request.provider.value)

        # Verify provider is connected
        record = self.storage.get_provider(request.provider)
        if not record or not record["connected"]:
            logger.warning("Provider '%s' is not connected", request.provider.value)
            raise AppError(f"{request.provider.value} is not connected", 401, "missing_api_key")

        # Context-Aware Memory: send only the relevant prior turns, not the
        # full history. Provider-independent — identical for every provider.
        history = self.storage.history(request.conversation_id)
        packet, engine_ms = self.memory.build_context(request.conversation_id, request.message, history)
        messages = packet.to_chat_turns()
        logger.info(
            "Context: thread=%s | %d/%d msgs sent | %.2fms",
            packet.thread_id, packet.used_count, packet.total_history, engine_ms,
        )

        # Create provider adapter and send request
        credentials = self.providers.credentials(request.provider)
        logger.debug(
            "Credentials: api_key=%s, base_url=%s",
            "***" + (credentials.api_key[-4:] if credentials.api_key and len(credentials.api_key) > 4 else "set") if credentials.api_key else "NONE",
            credentials.base_url or "default",
        )

        adapter = ProviderFactory.create(request.provider, credentials)

        try:
            response = await adapter.chat(request.model, messages)
            logger.info(
                "=== CHAT SUCCESS === provider=%s | model=%s | response_length=%d",
                request.provider.value, request.model, len(response),
            )
        except Exception:
            logger.error(
                "=== CHAT FAILED === provider=%s | model=%s\n%s",
                request.provider.value, request.model, traceback.format_exc(),
            )
            raise

        # Persist messages with their thread + keywords for the memory engine.
        keywords_csv = self.memory.keywords_csv(request.message)
        self.storage.save_message(
            request.conversation_id, "user", request.message, request.provider, request.model,
            thread_id=packet.thread_id, keywords=keywords_csv,
        )
        created_at = self.storage.save_message(
            request.conversation_id, "assistant", response, request.provider, request.model,
            thread_id=packet.thread_id,
        )
        return ChatResponse(
            conversation_id=request.conversation_id,
            provider=request.provider,
            model=request.model,
            response=response,
            created_at=datetime.fromisoformat(created_at),
            context=self.memory.to_context_info(packet, engine_ms),
        )

    def history(self, conversation_id: str) -> list[HistoryMessage]:
        return [HistoryMessage.model_validate(item) for item in self.storage.history(conversation_id)]
