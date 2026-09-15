"""FastAPI router for the Repository Indexing Engine.

Self-contained and additive: exposes ``POST /repository/index/build`` and wires
its own engine singleton (embedding provider + ChromaDB store + chunk
generator) from configuration. All engine errors — Ollama down, embedding
timeout, ChromaDB missing, invalid repo — are mapped to a structured
``{ error, detail }`` envelope with the matching HTTP status. Mounting is a
single additive ``app.include_router(...)`` call.
"""

from __future__ import annotations

import logging
from functools import lru_cache

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from app.services.repository.chunker import ChunkGenerator
from app.services.repository.embedding_config import embedding_settings
from app.services.repository.embedding_models import IndexBuildRequest, IndexBuildResponse
from app.services.repository.embedding_service import EmbeddingService, create_embedding_provider
from app.services.repository.exceptions import RepositoryError
from app.services.repository.repository_indexer import RepositoryIndexingEngine
from app.services.repository.vector_store import ChromaVectorStore

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/repository/index", tags=["repository-indexing"])


@lru_cache(maxsize=1)
def _default_engine() -> RepositoryIndexingEngine:
    """Process-wide singleton. Providers/registries built once; ChromaDB is
    connected lazily on first indexing call, so constructing this never fails
    even if chromadb isn't installed yet."""
    config = embedding_settings
    provider = create_embedding_provider(config)
    service = EmbeddingService(provider, config.batch_size)
    store = ChromaVectorStore(config)
    generator = ChunkGenerator()
    return RepositoryIndexingEngine(generator, service, store, config)


def get_indexing_engine() -> RepositoryIndexingEngine:
    """FastAPI dependency; override via ``app.dependency_overrides`` in tests."""
    return _default_engine()


@router.post("/build", response_model=IndexBuildResponse)
def build_index(
    request: IndexBuildRequest,
    engine: RepositoryIndexingEngine = Depends(get_indexing_engine),
) -> IndexBuildResponse | JSONResponse:
    """Build/refresh the vector index for a repository (incremental).

    Returns the repository summary, indexing statistics, collection name,
    embedding model, and per-action counts (embedded/updated/skipped/deleted).
    """
    try:
        return engine.build_index(request)
    except RepositoryError as exc:
        logger.warning("Index build failed [%s]: %s", exc.code, exc.detail)
        return JSONResponse(status_code=exc.status_code, content={"error": exc.code, "detail": exc.detail})
    except Exception as exc:  # defensive: never leak a raw traceback
        logger.exception("Unexpected index build error")
        return JSONResponse(status_code=500, content={"error": "internal_error", "detail": str(exc)})
