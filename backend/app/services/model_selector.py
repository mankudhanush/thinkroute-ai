from __future__ import annotations

import logging
import time

from app.models.schemas import ModelInfo, ProviderId
from app.services.storage_service import StorageService

logger = logging.getLogger(__name__)

# How long a resolved model selection stays cached before we re-check the DB.
_SELECTION_TTL_SECONDS = 60.0

# Preferred models per provider (ordered by priority, highest first).
# These are used as preference hints — the selector reads actual available
# models dynamically from the database and matches against this list.
PREFERRED_MODELS: dict[ProviderId, list[str]] = {
    ProviderId.GEMINI: [
        "gemini-2.5-pro",
        "gemini-2.5-flash",
        "gemini-2.0-flash",
        "gemini-2.0-flash-001",
        "gemini-2.0-flash-lite",
        "gemini-1.5-pro",
        "gemini-1.5-flash",
    ],
    ProviderId.GROQ: [
        "llama-3.3-70b-versatile",
        "llama-3.1-70b-versatile",
        "llama-3.1-8b-instant",
        "llama3-70b-8192",
        "llama3-8b-8192",
        "mixtral-8x7b-32768",
        "gemma2-9b-it",
    ],
    ProviderId.CLOUDFLARE: [
        "@cf/meta/llama-3.1-8b-instruct",
        "@cf/meta/llama-3-8b-instruct",
        "@cf/mistral/mistral-7b-instruct-v0.1",
        "@cf/google/gemma-7b-it",
    ],
    ProviderId.OLLAMA: [
        "qwen3:4b",
        "llama3.2:3b",
        "qwen2.5-coder:7b",
    ],
}


class ModelSelector:
    def __init__(self, storage: StorageService) -> None:
        self.storage = storage
        # provider → (selected_model, expires_at_monotonic)
        self._cache: dict[ProviderId, tuple[str, float]] = {}

    def invalidate(self, provider: ProviderId | None = None) -> None:
        """Drop cached selections (call after (re)connecting/refreshing)."""
        if provider is None:
            self._cache.clear()
        else:
            self._cache.pop(provider, None)

    def select(self, provider: ProviderId, intent_model: str | None = None) -> str | None:
        """Select the best available model for a provider.

        Args:
            provider: The provider to select a model for.
            intent_model: The model used for intent classification.
                          If the provider is Ollama and the intent model
                          is in the available list, we still allow it
                          because the routing engine intentionally chose Ollama.
        """
        cached = self._cache.get(provider)
        if cached is not None and cached[1] > time.monotonic():
            return cached[0]

        # Read available models dynamically from the database
        available = self.storage.get_models(provider)
        if not available:
            logger.warning("[ModelSelector] No models available for '%s'", provider.value)
            return None

        available_ids = {m.id for m in available}

        # Never re-select a model the validation agent has ever confirmed
        # broken (deprecated, quota-exhausted, etc.) — that signal doesn't
        # go stale the way a past success does, so it isn't time-boxed.
        bad_ids = set(self.storage.get_known_bad_models(provider))
        usable_ids = available_ids - bad_ids or available_ids

        # Within what's usable, prefer models confirmed working recently.
        valid_ids = set(self.storage.get_valid_models(provider))
        candidate_ids = (usable_ids & valid_ids) or usable_ids

        preferred = PREFERRED_MODELS.get(provider, [])

        # Try preferred models in priority order
        for model_id in preferred:
            if model_id in candidate_ids:
                logger.info(
                    "[ModelSelector] Selected preferred model '%s' for '%s'",
                    model_id, provider.value,
                )
                return self._cache_and_return(provider, model_id)

        # Fall back to the first candidate model, preserving the provider's
        # original ordering, rather than an arbitrary/known-bad one.
        fallback_pool = [m.id for m in available if m.id in candidate_ids]
        fallback = fallback_pool[0]
        logger.info(
            "[ModelSelector] No preferred model matched for '%s', falling back to '%s'",
            provider.value, fallback,
        )
        return self._cache_and_return(provider, fallback)

    def _cache_and_return(self, provider: ProviderId, model_id: str) -> str:
        self._cache[provider] = (model_id, time.monotonic() + _SELECTION_TTL_SECONDS)
        return model_id
