"""Pydantic models & enums for the Repository Intelligence Engine.

These types are the stable contract between the scanner, parser, detector,
aggregator, and the FastAPI layer — and, crucially, the contract that future
phases (Chunk Generator, Embedding Engine, Dependency Graph, Patch Generator)
will consume. They are therefore designed to be *additive-friendly*: every
symbol carries line spans and a stable ``relative_path`` so downstream tooling
can chunk, embed, or diff without re-parsing.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class Language(str, Enum):
    """Recognised source languages. ``UNKNOWN`` covers catalogued-but-unmapped
    files so nothing is silently dropped from statistics."""

    PYTHON = "python"
    JAVASCRIPT = "javascript"
    JSX = "jsx"
    TYPESCRIPT = "typescript"
    TSX = "tsx"
    JAVA = "java"
    KOTLIN = "kotlin"
    GO = "go"
    RUST = "rust"
    CSHARP = "csharp"
    DART = "dart"
    HTML = "html"
    CSS = "css"
    SCSS = "scss"
    VUE = "vue"
    SVELTE = "svelte"
    JSON = "json"
    MARKDOWN = "markdown"
    YAML = "yaml"
    XML = "xml"
    TOML = "toml"
    SHELL = "shell"
    SQL = "sql"
    UNKNOWN = "unknown"


class FileCategory(str, Enum):
    SOURCE = "source"
    CONFIG = "config"
    DOCUMENTATION = "documentation"
    STYLE = "style"
    MARKUP = "markup"
    DATA = "data"
    OTHER = "other"


class SymbolKind(str, Enum):
    FUNCTION = "function"
    METHOD = "method"
    CLASS = "class"
    INTERFACE = "interface"
    TYPE = "type"
    ENUM = "enum"
    COMPONENT = "component"
    HOOK = "hook"
    VARIABLE = "variable"


# ---------------------------------------------------------------------------
# Symbol-level metadata
# ---------------------------------------------------------------------------


class ImportMetadata(BaseModel):
    """A single import/require/use statement."""

    module: str = Field(description="The imported module/package specifier.")
    names: list[str] = Field(default_factory=list, description="Imported symbol names, if enumerated.")
    alias: str | None = None
    is_relative: bool = Field(default=False, description="Relative/local import (starts with '.' or '/').")
    is_external: bool = Field(default=False, description="Resolved to a third-party dependency.")
    level: int = Field(default=0, description="Python relative-import depth (0 = absolute).")
    line: int = 0
    raw: str = ""


class ExportMetadata(BaseModel):
    name: str
    kind: SymbolKind = SymbolKind.VARIABLE
    is_default: bool = False
    line: int = 0


class FunctionMetadata(BaseModel):
    name: str
    is_async: bool = False
    is_method: bool = False
    is_exported: bool = False
    decorators: list[str] = Field(default_factory=list)
    parameters: list[str] = Field(default_factory=list)
    returns: str | None = None
    line_start: int = 0
    line_end: int = 0


class ClassMetadata(BaseModel):
    name: str
    bases: list[str] = Field(default_factory=list)
    decorators: list[str] = Field(default_factory=list)
    methods: list[FunctionMetadata] = Field(default_factory=list)
    is_exported: bool = False
    line_start: int = 0
    line_end: int = 0


class SymbolMetadata(BaseModel):
    """Generic named symbol used for interfaces, types, and enums."""

    name: str
    kind: SymbolKind
    is_exported: bool = False
    line: int = 0


class ComponentMetadata(BaseModel):
    """A UI component (React/Vue/Angular/Svelte)."""

    name: str
    kind: str = "function"  # "function" | "class"
    hooks: list[str] = Field(default_factory=list)
    is_exported: bool = False
    line: int = 0


class DependencyMetadata(BaseModel):
    """Per-file dependency breakdown, ready for the future Dependency Graph."""

    internal: list[str] = Field(default_factory=list, description="Imports resolving inside the repo.")
    external: list[str] = Field(default_factory=list, description="Third-party package imports.")
    relative: list[str] = Field(default_factory=list, description="Relative import specifiers.")


# ---------------------------------------------------------------------------
# File / directory metadata
# ---------------------------------------------------------------------------


class FileMetadata(BaseModel):
    """Everything known about a single file after scanning and parsing."""

    relative_path: str
    absolute_path: str
    name: str
    extension: str
    language: Language
    category: FileCategory
    framework: str | None = None
    is_config: bool = False

    size_bytes: int = 0
    size_human: str = "0 B"
    line_count: int = 0
    #: Stable content hash — the seam for future *incremental* re-indexing
    #: (skip files whose hash is unchanged).
    content_hash: str = ""

    imports: list[ImportMetadata] = Field(default_factory=list)
    exports: list[ExportMetadata] = Field(default_factory=list)
    functions: list[FunctionMetadata] = Field(default_factory=list)
    classes: list[ClassMetadata] = Field(default_factory=list)
    components: list[ComponentMetadata] = Field(default_factory=list)
    hooks: list[str] = Field(default_factory=list)
    interfaces: list[SymbolMetadata] = Field(default_factory=list)
    types: list[SymbolMetadata] = Field(default_factory=list)
    enums: list[SymbolMetadata] = Field(default_factory=list)
    decorators: list[str] = Field(default_factory=list)
    async_functions: list[str] = Field(default_factory=list)

    dependencies: DependencyMetadata = Field(default_factory=DependencyMetadata)

    #: Populated when a recoverable parse problem occurred; the file is still
    #: catalogued with whatever metadata could be recovered.
    parse_error: str | None = None


class DirectoryMetadata(BaseModel):
    relative_path: str
    name: str
    file_count: int = 0
    subdirectory_count: int = 0
    languages: dict[str, int] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Repository-level metadata
# ---------------------------------------------------------------------------


class FrameworkDetection(BaseModel):
    name: str
    category: str
    confidence: float = Field(ge=0.0, le=1.0)
    evidence: list[str] = Field(default_factory=list)


class LargestFile(BaseModel):
    relative_path: str
    size_bytes: int
    size_human: str


class RepositoryStatistics(BaseModel):
    total_files: int = 0
    supported_files: int = 0
    parsed_files: int = 0
    failed_files: int = 0
    ignored_files: int = 0
    directory_count: int = 0

    primary_language: Language | None = None
    secondary_languages: list[Language] = Field(default_factory=list)
    language_breakdown: dict[str, int] = Field(default_factory=dict)

    total_size_bytes: int = 0
    total_lines: int = 0
    average_file_size_bytes: float = 0.0
    largest_file: LargestFile | None = None


class RepositoryMetadata(BaseModel):
    name: str
    root_path: str
    primary_framework: FrameworkDetection | None = None
    frameworks: list[FrameworkDetection] = Field(default_factory=list)
    primary_language: Language | None = None
    languages: list[Language] = Field(default_factory=list)
    scanned_at: datetime
    duration_ms: float = 0.0


# ---------------------------------------------------------------------------
# API request / response
# ---------------------------------------------------------------------------


class RepositoryIndexRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    repository_path: str = Field(min_length=1, description="Absolute or relative path to an extracted repository.")
    max_file_size_bytes: int | None = Field(
        default=None, ge=1, description="Override the default per-file size limit for this run."
    )
    include_files: bool = Field(
        default=True, description="Include the per-file metadata array in the response."
    )


class RepositoryIndexResponse(BaseModel):
    """Matches the required response envelope:
    ``{ repository, framework, statistics, files }``."""

    repository: RepositoryMetadata
    framework: FrameworkDetection | None = None
    statistics: RepositoryStatistics
    files: list[FileMetadata] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Internal transfer object (not exposed over the API)
# ---------------------------------------------------------------------------


class ScannedFile(BaseModel):
    """Lightweight record produced by the scanner before parsing.

    Kept separate from :class:`FileMetadata` so the scanning stage can stream
    millions of entries cheaply without carrying parse fields around — the seam
    for future incremental / streaming indexing of 100k+ file repositories.
    """

    absolute_path: str
    relative_path: str
    name: str
    extension: str
    size_bytes: int
    language: Language
