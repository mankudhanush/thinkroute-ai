"""FastAPI router for the Intelligent Chunk Generator.

Self-contained and additive: it builds its own :class:`ChunkGenerator`
singleton (parser/strategy registries built once) and maps the module's
exceptions to structured HTTP responses. Mounting is a single additive
``app.include_router(...)`` call — it adds ``POST /repository/chunks`` without
touching any existing route.
"""

from __future__ import annotations

import logging
from functools import lru_cache

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from app.services.repository.chunk_models import (
    ChunkGenerationRequest,
    ChunkGenerationResponse,
)
from app.services.repository.chunker import ChunkGenerator
from app.services.repository.exceptions import RepositoryError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/repository", tags=["repository-chunks"])


@lru_cache(maxsize=1)
def _default_generator() -> ChunkGenerator:
    """Process-wide singleton; parser + strategy registries built once."""
    return ChunkGenerator()


def get_chunk_generator() -> ChunkGenerator:
    """FastAPI dependency; override via ``app.dependency_overrides`` in tests."""
    return _default_generator()


@router.post("/chunks", response_model=ChunkGenerationResponse)
def generate_chunks(
    request: ChunkGenerationRequest,
    generator: ChunkGenerator = Depends(get_chunk_generator),
) -> ChunkGenerationResponse | JSONResponse:
    """Generate semantic chunks for an extracted repository.

    Returns ``{ summary, statistics, chunks }``. Engine errors map to a
    structured ``{ error, detail }`` envelope with the matching status code.
    """
    try:
        return generator.generate(request)
    except RepositoryError as exc:
        logger.warning("Chunk generation failed [%s]: %s", exc.code, exc.detail)
        return JSONResponse(status_code=exc.status_code, content={"error": exc.code, "detail": exc.detail})
    except Exception as exc:  # defensive: never leak a raw traceback
        logger.exception("Unexpected chunk generation error")
        return JSONResponse(status_code=500, content={"error": "internal_error", "detail": str(exc)})
