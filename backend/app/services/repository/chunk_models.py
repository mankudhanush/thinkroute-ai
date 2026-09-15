"""Pydantic models for the Intelligent Chunk Generator.

A *chunk* is one semantically-complete unit of code (a function, class,
method, React component, hook, interface, whole config file, …) enriched with
enough metadata that an LLM — or a downstream Embedding / ChromaDB / Retrieval
phase — can reason about it without ever re-reading the source file.

These models are the stable contract for every future phase, so they carry:
  * a **deterministic** ``chunk_id`` (stable across re-indexing),
  * dependency + relationship metadata for dependency-aware retrieval,
  * a content ``hash`` so incremental re-embedding can skip unchanged chunks.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from app.services.repository.models import Language


class ChunkType(str, Enum):
    """The semantic kind of a chunk. Broad enough to cover every supported
    language while staying meaningful to retrieval/ranking downstream."""

    FUNCTION = "function"
    ASYNC_FUNCTION = "async_function"
    METHOD = "method"
    CLASS = "class"
    DATACLASS = "dataclass"
    ENUM = "enum"
    INTERFACE = "interface"
    TYPE_ALIAS = "type_alias"
    RECORD = "record"
    STRUCT = "struct"
    TRAIT = "trait"
    COMPONENT = "component"
    HOOK = "hook"
    CONTEXT_PROVIDER = "context_provider"
    UTILITY_FUNCTION = "utility_function"
    MODULE_CONSTANTS = "module_constants"
    CONFIG_FILE = "config_file"
    DOCUMENT = "document"
    STYLE = "style"
    MARKUP = "markup"
    DATA = "data"
    MODULE = "module"
    #: A logical sub-section of an oversized symbol (split on blank-line /
    #: block boundaries — never on arbitrary line counts).
    BLOCK = "block"


class Visibility(str, Enum):
    PUBLIC = "public"
    PRIVATE = "private"
    PROTECTED = "protected"
    INTERNAL = "internal"


class RelationshipType(str, Enum):
    """Directed relationship from a chunk to a related chunk/symbol."""

    METHOD_OF = "method_of"          # method  -> owning class
    HAS_METHOD = "has_method"        # class   -> its method
    USES_HOOK = "uses_hook"          # component -> hook it calls
    USES_UTILITY = "uses_utility"    # chunk   -> utility it imports/calls
    USES_TYPE = "uses_type"          # component/fn -> interface/type it uses
    PART_OF = "part_of"              # block   -> parent symbol
    HAS_PART = "has_part"            # symbol  -> its split block
    EXTENDS = "extends"              # class   -> base class
    IMPORTS = "imports"              # chunk   -> imported module symbol


class ChunkDependency(BaseModel):
    """One imported symbol that a chunk actually references in its body."""

    name: str = Field(description="Referenced imported symbol (e.g. 'Button').")
    module: str = Field(description="Import specifier it came from (e.g. './Button').")
    is_external: bool = False
    is_relative: bool = False


class ChunkRelationship(BaseModel):
    """A link to another chunk. ``target_chunk_id`` is populated for in-file
    relationships resolved at generation time; cross-file links carry only
    ``target_symbol`` for a later retrieval phase to resolve."""

    relation: RelationshipType
    target_symbol: str
    target_chunk_id: str | None = None


class Chunk(BaseModel):
    """A single semantic chunk with full context for standalone understanding."""

    model_config = ConfigDict(use_enum_values=True)

    # --- identity ---
    repository_id: str
    repository_name: str
    chunk_id: str
    chunk_type: ChunkType

    # --- location ---
    language: Language
    framework: str | None = None
    file_path: str
    relative_path: str
    start_line: int
    end_line: int

    # --- symbol ---
    symbol_name: str
    parent_symbol: str | None = None
    signature: str | None = None
    is_async: bool = False
    decorators: list[str] = Field(default_factory=list)
    visibility: Visibility = Visibility.PUBLIC

    # --- graph / dependencies ---
    imports: list[str] = Field(default_factory=list, description="Referenced imported names.")
    exports: list[str] = Field(default_factory=list, description="Symbols this chunk exports.")
    dependencies: list[ChunkDependency] = Field(default_factory=list)
    relationships: list[ChunkRelationship] = Field(default_factory=list)

    # --- content ---
    hash: str
    content: str = ""
    line_count: int = 0
    char_count: int = 0
    token_estimate: int = 0

    # --- split bookkeeping (BLOCK chunks of an oversized symbol) ---
    part_index: int | None = None
    part_total: int | None = None


class ChunkSizeRef(BaseModel):
    chunk_id: str
    symbol_name: str
    char_count: int
    line_count: int


class ChunkStatistics(BaseModel):
    total_chunks: int = 0
    total_files: int = 0
    files_with_chunks: int = 0

    chunks_per_file: dict[str, int] = Field(default_factory=dict)
    chunks_per_language: dict[str, int] = Field(default_factory=dict)
    chunks_per_framework: dict[str, int] = Field(default_factory=dict)
    chunks_per_type: dict[str, int] = Field(default_factory=dict)

    average_chunk_chars: float = 0.0
    average_chunk_lines: float = 0.0
    largest_chunk: ChunkSizeRef | None = None
    smallest_chunk: ChunkSizeRef | None = None


class ChunkSummary(BaseModel):
    repository_id: str
    repository_name: str
    root_path: str
    primary_language: Language | None = None
    primary_framework: str | None = None
    languages: list[Language] = Field(default_factory=list)
    frameworks: list[str] = Field(default_factory=list)
    total_files: int = 0
    total_chunks: int = 0
    generated_at: datetime
    duration_ms: float = 0.0


# --- API request / response -------------------------------------------------


class ChunkGenerationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    repository_path: str = Field(min_length=1)
    max_file_size_bytes: int | None = Field(default=None, ge=1)
    #: Split any single symbol larger than this into semantic BLOCK chunks.
    max_chunk_lines: int | None = Field(default=None, ge=20)
    #: Set false to return metadata only (omit ``content``) — lighter payloads
    #: for very large repositories.
    include_content: bool = True


class ChunkGenerationResponse(BaseModel):
    summary: ChunkSummary
    statistics: ChunkStatistics
    chunks: list[Chunk] = Field(default_factory=list)
