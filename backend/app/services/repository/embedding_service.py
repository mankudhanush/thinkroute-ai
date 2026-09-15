"""Embedding service — pluggable provider architecture.

The indexer depends only on the :class:`EmbeddingProvider` protocol and the
:class:`EmbeddingService` batcher, never on a concrete backend, so a future
OpenAI / Gemini / Cohere / Jina / HuggingFace provider drops in by implementing
one method and registering in :func:`create_embedding_provider` — no indexer
change (Open/Closed + Dependency Inversion).

This phase ships the Ollama provider (default model ``nomic-embed-text``, taken
from configuration — never hard-coded). All embedding is **batched**; the
service never calls the provider one text at a time.
"""

from __future__ import annotations

import logging
import time
from typing import Protocol

import httpx

from app.services.repository.embedding_config import EmbeddingSettings
from app.services.repository.exceptions import RepositoryError

logger = logging.getLogger(__name__)

# nomic-embed-text has an 8192-token context window; ~4 chars/token → 8000 chars
# is a safe ceiling that avoids Ollama HTTP 500 context-overflow errors.
_MAX_EMBED_CHARS = 8_000


# ---------------------------------------------------------------------------
# Errors (structured; mapped to HTTP by the router)
# ---------------------------------------------------------------------------


class EmbeddingError(RepositoryError):
    status_code = 502
    code = "embedding_failed"


class EmbeddingProviderUnavailableError(EmbeddingError):
    status_code = 503
    code = "embedding_provider_unavailable"


class EmbeddingTimeoutError(EmbeddingError):
    status_code = 504
    code = "embedding_timeout"


class EmbeddingConfigurationError(EmbeddingError):
    status_code = 400
    code = "embedding_configuration_error"


# ---------------------------------------------------------------------------
# Provider interface
# ---------------------------------------------------------------------------


class EmbeddingProvider(Protocol):
    """Contract every embedding backend implements."""

    name: str
    model: str

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Return one embedding vector per input text, order-preserving."""
        ...

    def health_check(self) -> bool:
        """Cheap liveness probe used before a large indexing run."""
        ...


# ---------------------------------------------------------------------------
# Ollama provider
# ---------------------------------------------------------------------------


class OllamaEmbeddingProvider:
    """Embeddings via a local Ollama server.

    Prefers the batch ``/api/embed`` endpoint and falls back to the legacy
    per-item ``/api/embeddings`` endpoint on older Ollama versions.
    """

    name = "ollama"

    def __init__(self, config: EmbeddingSettings) -> None:
        self._base_url = config.ollama_base_url.rstrip("/")
        self.model = config.model
        self._timeout = config.request_timeout_seconds
        self._max_retries = config.max_retries
        self._use_batch_endpoint = True  # flipped off if /api/embed is absent

    def health_check(self) -> bool:
        try:
            with httpx.Client(timeout=5.0) as client:
                return client.get(f"{self._base_url}/api/tags").status_code == 200
        except httpx.HTTPError:
            return False

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        last_exc: Exception | None = None
        for attempt in range(self._max_retries + 1):
            try:
                if self._use_batch_endpoint:
                    return self._embed_via_batch(texts)
                return self._embed_via_single(texts)
            except EmbeddingProviderUnavailableError:
                raise  # not worth retrying a down server within the loop tail
            except (httpx.TimeoutException,) as exc:
                last_exc = exc
                logger.warning("Embedding timeout (attempt %d/%d)", attempt + 1, self._max_retries + 1)
            except EmbeddingError as exc:
                last_exc = exc
                logger.warning("Embedding error (attempt %d/%d): %s", attempt + 1, self._max_retries + 1, exc.detail)
        if isinstance(last_exc, httpx.TimeoutException):
            raise EmbeddingTimeoutError(f"Ollama embedding timed out after {self._max_retries + 1} attempts.")
        raise EmbeddingError(f"Ollama embedding failed: {last_exc}")

    # -- endpoints ----------------------------------------------------------

    @staticmethod
    def _truncate(text: str) -> str:
        """Trim text to the safe context-window ceiling before sending to Ollama."""
        return text[:_MAX_EMBED_CHARS] if len(text) > _MAX_EMBED_CHARS else text

    def _embed_via_batch(self, texts: list[str]) -> list[list[float]]:
        safe_texts = [self._truncate(t) for t in texts]
        try:
            with httpx.Client(timeout=self._timeout) as client:
                response = client.post(
                    f"{self._base_url}/api/embed",
                    json={"model": self.model, "input": safe_texts},
                )
        except httpx.ConnectError as exc:
            raise EmbeddingProviderUnavailableError(
                f"Cannot reach Ollama at {self._base_url}. Is it running? ({exc})"
            ) from exc

        if response.status_code == 404:  # older Ollama without /api/embed
            logger.info("Ollama /api/embed not found; using legacy /api/embeddings")
            self._use_batch_endpoint = False
            return self._embed_via_single(texts)

        if response.status_code >= 500:
            # Batch-level 500 — try one-by-one so a single bad chunk doesn't
            # abort the whole indexing run.
            logger.warning(
                "Ollama batch embed returned HTTP %d; falling back to per-item embedding",
                response.status_code,
            )
            return self._embed_via_single(texts)

        self._raise_for_status(response)
        data = response.json()
        vectors = data.get("embeddings")
        if not isinstance(vectors, list) or len(vectors) != len(texts):
            raise EmbeddingError("Ollama /api/embed returned an unexpected payload shape.")
        return vectors

    def _embed_via_single(self, texts: list[str]) -> list[list[float]]:
        """Embed one text at a time. Skips (zero-vector) items that still fail
        so a single oversized/corrupt chunk never aborts the whole indexing run."""
        vectors: list[list[float]] = []
        try:
            with httpx.Client(timeout=self._timeout) as client:
                for text in texts:
                    safe_text = self._truncate(text)
                    response = client.post(
                        f"{self._base_url}/api/embeddings",
                        json={"model": self.model, "prompt": safe_text},
                    )
                    if response.status_code >= 500:
                        logger.warning(
                            "Ollama returned HTTP %d for a single chunk; skipping with zero vector",
                            response.status_code,
                        )
                        vectors.append([0.0] * 768)  # nomic-embed-text dim
                        continue
                    self._raise_for_status(response)
                    vector = response.json().get("embedding")
                    if not isinstance(vector, list):
                        raise EmbeddingError("Ollama /api/embeddings returned no embedding.")
                    vectors.append(vector)
        except httpx.ConnectError as exc:
            raise EmbeddingProviderUnavailableError(
                f"Cannot reach Ollama at {self._base_url}. Is it running? ({exc})"
            ) from exc
        return vectors

    @staticmethod
    def _raise_for_status(response: httpx.Response) -> None:
        if response.status_code == 404:
            raise EmbeddingConfigurationError(
                "Embedding model not found on Ollama. Run: ollama pull <model>."
            )
        if response.status_code >= 500:
            raise EmbeddingProviderUnavailableError(f"Ollama server error (HTTP {response.status_code}).")
        if response.status_code >= 400:
            raise EmbeddingError(f"Ollama embedding request failed (HTTP {response.status_code}).")


# ---------------------------------------------------------------------------
# Provider factory (the pluggable seam)
# ---------------------------------------------------------------------------

#: Providers planned for future phases — named here so the error message is
#: actionable and the extension point is obvious.
_KNOWN_FUTURE_PROVIDERS = ("openai", "gemini", "cohere", "jina", "huggingface")


def create_embedding_provider(config: EmbeddingSettings) -> EmbeddingProvider:
    provider = config.provider.lower()
    if provider == "ollama":
        return OllamaEmbeddingProvider(config)
    if provider in _KNOWN_FUTURE_PROVIDERS:
        raise EmbeddingConfigurationError(
            f"Embedding provider '{provider}' is planned but not yet implemented; "
            f"currently supported: 'ollama'."
        )
    raise EmbeddingConfigurationError(f"Unknown embedding provider '{config.provider}'.")


# ---------------------------------------------------------------------------
# Batching service (what the indexer calls)
# ---------------------------------------------------------------------------


class EmbeddingService:
    """Batches texts to the provider. Tracks batch count + cumulative time so
    the indexer can report embedding statistics."""

    def __init__(self, provider: EmbeddingProvider, batch_size: int) -> None:
        if batch_size < 1:
            raise EmbeddingConfigurationError("batch_size must be >= 1.")
        self._provider = provider
        self._batch_size = batch_size
        self.batches_run = 0
        self.total_embedding_ms = 0.0

    @property
    def model(self) -> str:
        return self._provider.model

    def health_check(self) -> bool:
        return self._provider.health_check()

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed ``texts`` in configured-size batches, preserving order."""
        vectors: list[list[float]] = []
        for start in range(0, len(texts), self._batch_size):
            batch = texts[start : start + self._batch_size]
            began = time.perf_counter()
            batch_vectors = self._provider.embed_batch(batch)
            elapsed = (time.perf_counter() - began) * 1000.0
            self.batches_run += 1
            self.total_embedding_ms += elapsed
            logger.info(
                "Embedding batch %d: %d texts in %.0fms (model=%s)",
                self.batches_run, len(batch), elapsed, self._provider.model,
            )
            vectors.extend(batch_vectors)
        return vectors
