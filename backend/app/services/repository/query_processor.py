"""Query processing for the Repository Retriever.

Normalises the user query (collapsing whitespace while preserving code
identifiers), generates exactly one query embedding by REUSING the existing
``EmbeddingService`` (no duplicated embedding logic), and validates that the
target repository is actually indexed before any search runs.

Kept deliberately small and mode-agnostic so future hybrid/keyword retrieval
can reuse the same normalised text and embedding without change.
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass

from app.services.repository.embedding_service import EmbeddingService
from app.services.repository.exceptions import RepositoryError
from app.services.repository.vector_store import VectorStore

logger = logging.getLogger(__name__)

_WHITESPACE_RE = re.compile(r"\s+")
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


class EmptyQueryError(RepositoryError):
    status_code = 400
    code = "empty_query"


class RepositoryNotIndexedError(RepositoryError):
    status_code = 404
    code = "repository_not_indexed"


@dataclass
class ProcessedQuery:
    """A normalised query plus its embedding and the timing to produce it."""

    raw: str
    normalized: str
    embedding: list[float]
    embedding_ms: float


class QueryProcessor:
    """Normalises, validates, and embeds a retrieval query."""

    def __init__(self, embedding_service: EmbeddingService, vector_store: VectorStore) -> None:
        self._embeddings = embedding_service
        self._store = vector_store

    @property
    def embedding_model(self) -> str:
        return self._embeddings.model

    # -- steps --------------------------------------------------------------

    @staticmethod
    def normalize(query: str) -> str:
        """Collapse whitespace and strip control chars WITHOUT altering code
        identifiers — no lowercasing, no punctuation stripping, so ``useAuth``,
        ``AuthService.login``, and ``src/components`` survive intact."""
        cleaned = _CONTROL_RE.sub(" ", query)
        cleaned = _WHITESPACE_RE.sub(" ", cleaned).strip()
        if not cleaned:
            raise EmptyQueryError("Query is empty after normalization.")
        return cleaned

    def ensure_indexed(self, collection: str, repository_id: str) -> None:
        """Fail fast if the repository has no vectors (never indexed)."""
        if self._store.count(collection) <= 0:
            raise RepositoryNotIndexedError(
                f"Repository '{repository_id}' is not indexed. Build its index first."
            )

    def embed(self, normalized: str) -> tuple[list[float], float]:
        """Generate ONE embedding for the query via the shared service."""
        began = time.perf_counter()
        vectors = self._embeddings.embed([normalized])
        elapsed = (time.perf_counter() - began) * 1000.0
        if not vectors or not vectors[0]:
            raise RepositoryError("Query embedding produced no vector.")
        return vectors[0], elapsed

    # -- orchestration ------------------------------------------------------

    def process(self, query: str, collection: str, repository_id: str) -> ProcessedQuery:
        normalized = self.normalize(query)
        self.ensure_indexed(collection, repository_id)
        embedding, embedding_ms = self.embed(normalized)
        logger.info(
            "Query processed: repo=%s len=%d embed=%.0fms",
            repository_id, len(normalized), embedding_ms,
        )
        return ProcessedQuery(
            raw=query, normalized=normalized, embedding=embedding, embedding_ms=embedding_ms
        )
