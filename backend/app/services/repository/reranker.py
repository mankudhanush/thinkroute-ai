"""Reranking stage for the Repository Retriever.

The retriever depends only on the :class:`Reranker` protocol, so the ranking
strategy is swappable. This phase ships :class:`VectorSimilarityReranker` — the
default — which orders candidates by their vector similarity adjusted for
chunk importance, chunk type, and dependency-expansion depth (the "result
ordering" the retriever requires).

A future cross-encoder / Jina / Cohere / OpenAI reranker implements the same
one-method interface and is selected via configuration — no retriever change.
"""

from __future__ import annotations

import logging
from typing import Protocol

from app.services.repository.exceptions import RepositoryError
from app.services.repository.query_processor import ProcessedQuery
from app.services.repository.retrieval_models import RetrievalSource, RetrievedChunk

logger = logging.getLogger(__name__)


class RerankerError(RepositoryError):
    status_code = 400
    code = "reranker_error"


class Reranker(Protocol):
    name: str

    def rerank(self, query: ProcessedQuery, candidates: list[RetrievedChunk]) -> list[RetrievedChunk]:
        """Return ``candidates`` reordered best-first; may also set rank_score."""
        ...


#: Relative importance by chunk type — defined symbols outrank raw blocks/data.
_TYPE_IMPORTANCE: dict[str, float] = {
    "component": 1.20,
    "context_provider": 1.18,
    "class": 1.15,
    "dataclass": 1.12,
    "function": 1.10,
    "async_function": 1.10,
    "method": 1.08,
    "hook": 1.12,
    "utility_function": 1.05,
    "interface": 1.05,
    "type_alias": 1.02,
    "enum": 1.02,
    "record": 1.05,
    "struct": 1.05,
    "trait": 1.05,
    "config_file": 0.95,
    "module_constants": 0.9,
    "module": 0.85,
    "document": 0.8,
    "markup": 0.8,
    "style": 0.8,
    "data": 0.8,
    "block": 0.75,
}

#: Similarity retained per expansion hop — a dependency two hops away is less
#: central than a direct hit.
_DEPTH_DECAY = 0.82


class VectorSimilarityReranker:
    """Default reranker: composite of similarity × type importance × depth."""

    name = "vector"

    def rerank(self, query: ProcessedQuery, candidates: list[RetrievedChunk]) -> list[RetrievedChunk]:
        for chunk in candidates:
            chunk.rank_score = round(self._score(chunk), 6)
        candidates.sort(key=self._sort_key, reverse=True)
        return candidates

    @staticmethod
    def _score(chunk: RetrievedChunk) -> float:
        importance = _TYPE_IMPORTANCE.get(chunk.chunk_type, 1.0)
        depth_factor = _DEPTH_DECAY ** max(0, chunk.depth)
        # Expansion hits keep a modest floor so relevant dependencies aren't
        # dropped just because they weren't a direct semantic match.
        base = chunk.score if chunk.source is RetrievalSource.SEMANTIC else max(chunk.score, 0.35)
        return base * importance * depth_factor

    @staticmethod
    def _sort_key(chunk: RetrievedChunk) -> tuple[int, float, float]:
        # Direct semantic hits first (depth 0), then by composite score.
        return (0 if chunk.depth == 0 else 1) * -1, chunk.rank_score, chunk.score


_FUTURE_RERANKERS = ("cross_encoder", "jina", "cohere", "openai")


def create_reranker(name: str) -> Reranker:
    key = name.lower()
    if key in ("vector", "default", "similarity"):
        return VectorSimilarityReranker()
    if key in _FUTURE_RERANKERS:
        raise RerankerError(
            f"Reranker '{name}' is planned but not yet implemented; currently supported: 'vector'."
        )
    raise RerankerError(f"Unknown reranker '{name}'.")
