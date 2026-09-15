"""FastAPI router for the Repository Retriever.

Self-contained and additive: exposes ``POST /repository/retrieve`` and wires its
own retriever singleton (query processor + ChromaDB store + reranker) from
configuration, reusing the existing embedding provider. All engine errors —
repository not indexed, embedding failure, vector-store failure, empty query,
invalid reranker — map to a structured ``{ error, detail }`` envelope. Mounting
is a single additive ``app.include_router(...)`` call.
"""

from __future__ import annotations

import logging
from functools import lru_cache

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from app.services.repository.embedding_config import embedding_settings
from app.services.repository.embedding_service import EmbeddingService, create_embedding_provider
from app.services.repository.exceptions import RepositoryError
from app.services.repository.query_processor import QueryProcessor
from app.services.repository.reranker import create_reranker
from app.services.repository.retrieval_config import retrieval_settings
from app.services.repository.retrieval_models import RetrieveRequest, RetrieveResponse
from app.services.repository.retriever import RepositoryRetriever
from app.services.repository.vector_store import ChromaVectorStore

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/repository", tags=["repository-retrieval"])


@lru_cache(maxsize=1)
def _default_retriever() -> RepositoryRetriever:
    """Process-wide singleton. Reuses the same embedding provider and ChromaDB
    store as the indexer; ChromaDB connects lazily on first query so building
    this never fails even before chromadb is installed."""
    embed_provider = create_embedding_provider(embedding_settings)
    embedding_service = EmbeddingService(embed_provider, embedding_settings.batch_size)
    store = ChromaVectorStore(embedding_settings)
    processor = QueryProcessor(embedding_service, store)
    reranker = create_reranker(retrieval_settings.reranker)
    return RepositoryRetriever(processor, store, reranker, retrieval_settings, embedding_settings)


def get_retriever() -> RepositoryRetriever:
    """FastAPI dependency; override via ``app.dependency_overrides`` in tests."""
    return _default_retriever()


@router.post("/retrieve", response_model=RetrieveResponse)
def retrieve(
    request: RetrieveRequest,
    retriever: RepositoryRetriever = Depends(get_retriever),
) -> RetrieveResponse | JSONResponse:
    """Retrieve ranked, dependency-expanded chunks for a query over one
    repository's index. Returns results, expanded dependencies, and statistics."""
    try:
        return retriever.retrieve(request)
    except RepositoryError as exc:
        logger.warning("Retrieval failed [%s]: %s", exc.code, exc.detail)
        return JSONResponse(status_code=exc.status_code, content={"error": exc.code, "detail": exc.detail})
    except Exception as exc:  # defensive: never leak a raw traceback
        logger.exception("Unexpected retrieval error")
        return JSONResponse(status_code=500, content={"error": "internal_error", "detail": str(exc)})
