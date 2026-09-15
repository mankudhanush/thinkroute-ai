from __future__ import annotations

import logging

from app.errors import ProviderNotFoundError
from app.models.schemas import ProviderId
from app.providers.base_provider import BaseProvider, ProviderCredentials
from app.providers.cloudflare_provider import CloudflareProvider
from app.providers.groq_provider import GroqProvider
from app.providers.gemini_provider import GeminiProvider
from app.providers.ollama_provider import OllamaProvider

logger = logging.getLogger(__name__)


class ProviderFactory:
    _providers: dict[ProviderId, type[BaseProvider]] = {
        ProviderId.GEMINI: GeminiProvider,
        ProviderId.GROQ: GroqProvider,
        ProviderId.CLOUDFLARE: CloudflareProvider,
        ProviderId.OLLAMA: OllamaProvider,
    }

    # Cache adapter instances so we reuse the same client objects across
    # requests instead of rebuilding them each time. Keyed by the credentials
    # so a re-connect with a new API key transparently gets a fresh adapter.
    _cache: dict[tuple[ProviderId, str | None, str | None], BaseProvider] = {}

    @classmethod
    def create(cls, provider: ProviderId, credentials: ProviderCredentials) -> BaseProvider:
        adapter_cls = cls._providers.get(provider)
        if adapter_cls is None:
            logger.error("No adapter registered for provider '%s'", provider.value)
            raise ProviderNotFoundError(provider.value)

        cache_key = (provider, credentials.api_key, credentials.base_url)
        cached = cls._cache.get(cache_key)
        if cached is not None:
            return cached

        adapter = adapter_cls(credentials)
        cls._cache[cache_key] = adapter
        logger.debug("Created + cached %s adapter for '%s'", adapter_cls.__name__, provider.value)
        return adapter
