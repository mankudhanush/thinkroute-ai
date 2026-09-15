from __future__ import annotations

import logging
from datetime import datetime

from app.errors import MissingApiKeyError
from app.models.schemas import ConnectRequest, ConnectResponse, ModelInfo, ProviderId, ProviderStatus
from app.providers.base_provider import ProviderCredentials
from app.services.provider_factory import ProviderFactory
from app.services.storage_service import StorageService

logger = logging.getLogger(__name__)

PROVIDER_NAMES = {
    ProviderId.GEMINI: "Google Gemini",
    ProviderId.GROQ: "Groq",
    ProviderId.CLOUDFLARE: "Cloudflare Workers AI",
    ProviderId.OLLAMA: "Ollama",
}


class ProviderService:
    def __init__(self, storage: StorageService) -> None:
        self.storage = storage

    async def connect(self, request: ConnectRequest) -> ConnectResponse:
        logger.info("Connecting provider '%s'...", request.provider.value)
        if not request.api_key and request.provider != ProviderId.OLLAMA:
            raise MissingApiKeyError(request.provider.value)
        adapter = ProviderFactory.create(request.provider, ProviderCredentials(request.api_key, request.optional_base_url))
        await adapter.connect()
        models = await adapter.list_models()
        logger.info("Provider '%s' connected with %d models", request.provider.value, len(models))
        
        from app.services.validation_service import ValidationAgent
        agent = ValidationAgent(self.storage)
        valid_models = await agent.validate_models(request.provider, models, request.api_key, request.optional_base_url)
        
        self.storage.save_provider(request.provider, request.api_key, request.optional_base_url, models)
        return ConnectResponse(provider=request.provider, status="Connected", connected=True, available_models=valid_models)

    def disconnect(self, provider_id: ProviderId) -> None:
        logger.info("Disconnecting provider '%s'", provider_id.value)
        self.storage.delete_provider(provider_id)

    def list(self) -> list[ProviderStatus]:
        records = {}
        for item in self.storage.list_provider_records():
            try:
                records[ProviderId(item["provider"])] = item
            except ValueError:
                # Ignore providers in the DB that are no longer supported
                continue
                
        result = []
        for provider_id, name in PROVIDER_NAMES.items():
            record = records.get(provider_id)
            connected_at = datetime.fromisoformat(record["connected_at"]) if record and record["connected_at"] else None
            
            # Filter models using validation cache
            available_models = self.storage.get_models(provider_id)
            if record and record["connected"]:
                valid_ids = set(self.storage.get_valid_models(provider_id))
                available_models = [m for m in available_models if m.id in valid_ids]
            
            result.append(ProviderStatus(provider=provider_id, name=name, connected=bool(record and record["connected"]), available_models=available_models, connected_at=connected_at))
        return result

    def credentials(self, provider_id: ProviderId) -> ProviderCredentials:
        api_key, base_url = self.storage.get_credentials(provider_id)
        logger.debug(
            "Retrieved credentials for '%s': key=%s, base_url=%s",
            provider_id.value,
            "present" if api_key else "NONE",
            base_url or "default",
        )
        return ProviderCredentials(api_key, base_url)

    async def refresh_models(self, provider_id: ProviderId) -> list[ModelInfo]:
        logger.info("Refreshing models for provider '%s'...", provider_id.value)
        credentials = self.credentials(provider_id)
        if not credentials.api_key and provider_id != ProviderId.OLLAMA:
            raise MissingApiKeyError(provider_id.value)
            
        adapter = ProviderFactory.create(provider_id, credentials)
        models = await adapter.list_models()
        
        self.storage.clear_model_validation(provider_id)
        from app.services.validation_service import ValidationAgent
        agent = ValidationAgent(self.storage)
        valid_models = await agent.validate_models(provider_id, models, credentials.api_key, credentials.base_url)
        
        self.storage.save_provider(provider_id, credentials.api_key, credentials.base_url, models)
        return valid_models
