"""Repository Intelligence Engine — Phase 1.

Scanning, parsing, and metadata extraction for a source repository, exposed as
an independent, additive FastAPI module. No embeddings, vector store, RAG, or
editing here — those are later phases that plug into the interfaces defined in
this package (``ParserRegistry``, ``RepositoryIndexer``, the Pydantic models).

Mount into the existing app with a single additive line:

    from app.services.repository import router as repository_router
    app.include_router(repository_router)
"""

from __future__ import annotations

from app.services.repository.metadata import RepositoryIndexer
from app.services.repository.models import (
    RepositoryIndexRequest,
    RepositoryIndexResponse,
)
from app.services.repository.router import router

__all__ = [
    "router",
    "RepositoryIndexer",
    "RepositoryIndexRequest",
    "RepositoryIndexResponse",
]
