"""FastAPI router for the Repository Intelligence Engine.

Self-contained: it constructs its own indexer via a cached factory (no
dependency on ``app.main`` wiring) and translates the module's exception
hierarchy into HTTP responses. Mounting it is a single additive
``app.include_router(repository_router)`` call — it touches no existing route.
"""

from __future__ import annotations

import logging
from functools import lru_cache

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from app.services.repository.exceptions import RepositoryError
from app.services.repository.metadata import RepositoryIndexer
from app.services.repository.models import (
    RepositoryIndexRequest,
    RepositoryIndexResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/repository", tags=["repository"])


@lru_cache(maxsize=1)
def _default_indexer() -> RepositoryIndexer:
    """Process-wide singleton — parser registry (and the tree-sitter probe) is
    built once and reused across requests."""
    return RepositoryIndexer()


def get_indexer() -> RepositoryIndexer:
    """FastAPI dependency; override in tests via ``app.dependency_overrides``."""
    return _default_indexer()


@router.post("/index", response_model=RepositoryIndexResponse)
def index_repository(
    request: RepositoryIndexRequest,
    indexer: RepositoryIndexer = Depends(get_indexer),
) -> RepositoryIndexResponse | JSONResponse:
    """Scan, parse, and extract metadata for an extracted repository.

    Returns ``{ repository, framework, statistics, files }``. All engine errors
    are mapped to a structured ``{ error, detail }`` envelope with the matching
    HTTP status; unexpected errors surface as HTTP 500.
    """
    try:
        return indexer.index(request)
    except RepositoryError as exc:
        logger.warning("Repository index failed [%s]: %s", exc.code, exc.detail)
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": exc.code, "detail": exc.detail},
        )
    except Exception as exc:  # defensive: never leak a raw traceback
        logger.exception("Unexpected repository index error")
        return JSONResponse(
            status_code=500,
            content={"error": "internal_error", "detail": str(exc)},
        )


@router.get("/health", tags=["repository"])
def repository_health() -> dict[str, str]:
    """Liveness probe for the Repository Intelligence Engine module."""
    return {"status": "ok", "module": "repository-intelligence"}
