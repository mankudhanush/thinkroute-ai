"""Pydantic models for the Repository Retriever.

Defines the request envelope (query + filters + options), the rich per-result
model consumed by the future Context Builder / Conversation Memory, and the
retrieval statistics. Result fields are populated from the metadata the
Indexing phase persisted (dependencies, line spans, visibility, …) plus the
dependency edges resolved at retrieval time.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class RetrievalSource(str, Enum):
    SEMANTIC = "semantic"                       # a direct vector-search hit
    DEPENDENCY_EXPANSION = "dependency_expansion"  # pulled in via a dependency edge


class RetrievalFilters(BaseModel):
    """Optional metadata filters. All are ANDed together. ``path_prefix`` is
    applied post-query (Chroma ``where`` has no prefix operator)."""

    model_config = ConfigDict(extra="forbid")

    language: str | None = None
    framework: str | None = None
    chunk_type: str | None = None
    chunk_types: list[str] | None = None
    symbol: str | None = None
    visibility: str | None = None
    relative_path: str | None = None
    path_prefix: str | None = None


class ChunkDependencyInfo(BaseModel):
    name: str
    module: str
    is_external: bool = False


class RelationshipEdge(BaseModel):
    relation: str
    target_symbol: str
    target_chunk_id: str | None = None


class RetrievedChunk(BaseModel):
    repository_id: str
    chunk_id: str
    score: float
    rank_score: float
    chunk_type: str
    symbol: str
    parent_symbol: str = ""
    language: str
    framework: str = ""
    relative_path: str
    start_line: int
    end_line: int
    visibility: str = ""
    summary: str | None = None
    dependencies: list[ChunkDependencyInfo] = Field(default_factory=list)
    relationships: list[RelationshipEdge] = Field(default_factory=list)
    content: str = ""

    source: RetrievalSource = RetrievalSource.SEMANTIC
    depth: int = 0  # 0 = direct hit; >0 = dependency-expansion distance


class RetrievalStatistics(BaseModel):
    embedding_ms: float = 0.0
    vector_search_ms: float = 0.0
    expansion_ms: float = 0.0
    rerank_ms: float = 0.0
    total_ms: float = 0.0
    chunks_retrieved: int = 0      # direct semantic hits (after threshold)
    chunks_expanded: int = 0       # added via dependency expansion
    final_result_count: int = 0
    vector_queries: int = 0        # Chroma round-trips (search + expansion fetches)


class RetrieveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    repository_id: str = Field(min_length=1)
    query: str = Field(min_length=1, max_length=8000)
    top_k: int | None = Field(default=None, ge=1, le=200)
    filters: RetrievalFilters | None = None
    dependency_expansion: bool | None = None
    max_expansion_depth: int | None = Field(default=None, ge=0, le=5)
    similarity_threshold: float | None = Field(default=None, ge=0.0, le=1.0)


class RetrieveResponse(BaseModel):
    repository_id: str
    query: str
    collection_name: str
    embedding_model: str
    results: list[RetrievedChunk] = Field(default_factory=list)
    expanded_dependencies: list[str] = Field(default_factory=list)
    statistics: RetrievalStatistics
