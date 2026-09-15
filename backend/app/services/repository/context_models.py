"""Models for the Context Builder.

Turns ranked :class:`RetrievedChunk` results into an organised, token-budgeted
:class:`RepositoryContext` the Prompt Builder consumes. Chunks are grouped into
sections (primary, supporting dependencies, configuration, utilities, extra),
prioritised, compressed if needed, and trimmed to fit a target context window.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from app.services.repository.retrieval_models import RetrievalFilters


class ContextSection(str, Enum):
    PRIMARY = "primary"                     # direct semantic hits — the answer core
    SUPPORTING = "supporting_dependencies"  # dependency-expanded chunks
    CONFIGURATION = "configuration"         # config files
    UTILITIES = "utilities"                 # shared helpers / constants / modules
    ADDITIONAL = "additional_references"    # everything else that still fits


#: Named context windows → token budgets.
CONTEXT_WINDOWS: dict[str, int] = {
    "8k": 8_192,
    "16k": 16_384,
    "32k": 32_768,
    "64k": 65_536,
    "128k": 131_072,
}
DEFAULT_WINDOW_TOKENS = CONTEXT_WINDOWS["16k"]


class ContextRelationship(BaseModel):
    relation: str
    target_symbol: str
    target_chunk_id: str | None = None


class ContextChunk(BaseModel):
    chunk_id: str
    section: ContextSection
    symbol: str
    parent_symbol: str = ""
    chunk_type: str
    language: str
    framework: str = ""
    relative_path: str
    start_line: int
    end_line: int
    visibility: str = ""
    score: float = 0.0
    summary: str | None = None
    content: str = ""
    tokens: int = 0
    compressed: bool = False
    dependencies: list[str] = Field(default_factory=list)
    relationships: list[ContextRelationship] = Field(default_factory=list)


class ContextStatistics(BaseModel):
    window_tokens: int
    budget_tokens: int
    used_tokens: int
    included_chunks: int
    trimmed_chunks: int
    compressed_chunks: int
    duplicate_chunks_removed: int
    trimmed_symbols: list[str] = Field(default_factory=list)


class RepositoryContext(BaseModel):
    repository_id: str
    repository_name: str
    query: str
    summary: str = ""
    primary: list[ContextChunk] = Field(default_factory=list)
    supporting_dependencies: list[ContextChunk] = Field(default_factory=list)
    configuration: list[ContextChunk] = Field(default_factory=list)
    utilities: list[ContextChunk] = Field(default_factory=list)
    additional_references: list[ContextChunk] = Field(default_factory=list)
    statistics: ContextStatistics

    def all_chunks(self) -> list[ContextChunk]:
        return [
            *self.primary, *self.supporting_dependencies,
            *self.configuration, *self.utilities, *self.additional_references,
        ]


class ContextBuildRequest(BaseModel):
    """End-to-end request for ``POST /repository/context`` (retrieve + build)."""

    model_config = ConfigDict(extra="forbid")

    repository_id: str = Field(min_length=1)
    query: str = Field(min_length=1, max_length=8000)
    top_k: int | None = Field(default=None, ge=1, le=200)
    filters: RetrievalFilters | None = None
    dependency_expansion: bool | None = None
    max_expansion_depth: int | None = Field(default=None, ge=0, le=5)
    #: Either a named window ("8k".."128k") or an explicit token count.
    context_window: str | int = "16k"
    #: Fraction of the window reserved for the model's response.
    response_reserve_ratio: float = Field(default=0.35, ge=0.0, le=0.9)
