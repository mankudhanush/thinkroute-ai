"""Pydantic models & transfer objects for the Repository Indexing Engine.

Defines the stored-vector metadata contract (what a future Retriever / Context
Builder will filter and rank on), the API request/response envelope, and the
small internal transfer objects that flow between the indexer and the vector
store. Chunk *content* itself is stored as the Chroma "document"; this metadata
is everything needed to retrieve and reason about it later.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from app.services.repository.chunk_models import Chunk


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class ChunkAction(str, Enum):
    """What incremental indexing decided to do with a chunk."""

    INSERTED = "inserted"
    UPDATED = "updated"
    SKIPPED = "skipped"


# ---------------------------------------------------------------------------
# Stored metadata (Chroma requires scalar metadata values: str/int/float/bool)
# ---------------------------------------------------------------------------


class StoredChunkMetadata(BaseModel):
    """Metadata persisted alongside each vector. Serialised to scalars for
    Chroma via :meth:`to_chroma`; rich fields (dependencies) are JSON-encoded."""

    model_config = ConfigDict(use_enum_values=True)

    repository_id: str
    repository_name: str
    chunk_id: str
    chunk_type: str
    symbol: str
    parent_symbol: str = ""
    language: str
    framework: str = ""
    relative_path: str
    start_line: int
    end_line: int
    visibility: str
    dependencies: str = "[]"          # JSON: [{name, module, is_external}]
    dependency_modules: str = ""      # comma-joined, for cheap metadata filters
    content_hash: str
    embedding_version: str
    created_at: str
    updated_at: str

    @classmethod
    def from_chunk(
        cls,
        chunk: Chunk,
        *,
        embedding_version: str,
        created_at: str,
        updated_at: str,
    ) -> "StoredChunkMetadata":
        deps = [
            {"name": d.name, "module": d.module, "is_external": d.is_external}
            for d in chunk.dependencies
        ]
        modules = sorted({d.module for d in chunk.dependencies})
        return cls(
            repository_id=chunk.repository_id,
            repository_name=chunk.repository_name,
            chunk_id=chunk.chunk_id,
            chunk_type=str(chunk.chunk_type),
            symbol=chunk.symbol_name,
            parent_symbol=chunk.parent_symbol or "",
            language=str(chunk.language),
            framework=chunk.framework or "",
            relative_path=chunk.relative_path,
            start_line=chunk.start_line,
            end_line=chunk.end_line,
            visibility=str(chunk.visibility),
            dependencies=json.dumps(deps, separators=(",", ":")),
            dependency_modules=",".join(modules),
            content_hash=chunk.hash,
            embedding_version=embedding_version,
            created_at=created_at,
            updated_at=updated_at,
        )

    def to_chroma(self) -> dict[str, str | int | float | bool]:
        return self.model_dump()


# ---------------------------------------------------------------------------
# Internal transfer objects (indexer <-> vector store)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ExistingChunk:
    """The subset of stored metadata incremental indexing needs to compare."""

    content_hash: str
    embedding_version: str
    created_at: str


@dataclass
class UpsertRecord:
    """One vector to write: deterministic id + embedding + metadata + document."""

    id: str
    embedding: list[float]
    metadata: dict[str, str | int | float | bool]
    document: str


# ---------------------------------------------------------------------------
# API request / response
# ---------------------------------------------------------------------------


class IndexBuildRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    repository_path: str = Field(min_length=1)
    max_file_size_bytes: int | None = Field(default=None, ge=1)
    #: Override the configured embedding batch size for this run.
    batch_size: int | None = Field(default=None, ge=1)
    #: Override the configured embedding model for this run.
    model: str | None = None
    #: Force a full re-embed (ignore existing hashes) — e.g. after a model change.
    recreate: bool = False


class IndexStatistics(BaseModel):
    total_chunks: int = 0
    embedded_chunks: int = 0     # newly inserted
    updated_chunks: int = 0      # changed → re-embedded
    skipped_chunks: int = 0      # unchanged → reused
    deleted_chunks: int = 0      # removed from source → deleted from Chroma
    failed_chunks: int = 0
    embedding_batches: int = 0
    embedding_ms: float = 0.0
    indexing_ms: float = 0.0
    collection_size: int = 0


class IndexBuildResponse(BaseModel):
    repository_id: str
    repository_name: str
    root_path: str
    primary_language: str | None = None
    primary_framework: str | None = None
    collection_name: str
    embedding_model: str
    embedding_version: str

    chunks_embedded: int
    chunks_updated: int
    chunks_skipped: int
    chunks_deleted: int

    statistics: IndexStatistics
