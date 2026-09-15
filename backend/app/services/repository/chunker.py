"""Intelligent Chunk Generator.

Converts parsed repository metadata (Phase 1 ``Extraction`` objects) into
semantically-complete :class:`Chunk` records — never split by fixed
token/line/char counts, always by logical program units.

Pipeline (streaming, one file in memory at a time):

    scan → for each file: read once → parse → pick language strategy →
    emit chunks → link in-file relationships → accumulate statistics.

Design notes for the future Embedding/ChromaDB/Retrieval phases:
  * ``iter_chunks`` is a generator — consumers can embed/upsert incrementally
    without materialising a 100k-file repository.
  * Strategies are registered by :class:`Language`; adding a language never
    touches the generator (Open/Closed).
  * Every collaborator is injected, so parsing, scanning, and detection are
    swappable in tests and future parallel executors.
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Iterator, Protocol

from app.services.repository.chunk_models import (
    Chunk,
    ChunkGenerationRequest,
    ChunkGenerationResponse,
    ChunkRelationship,
    ChunkSizeRef,
    ChunkStatistics,
    ChunkSummary,
    ChunkType,
    RelationshipType,
)
from app.services.repository.chunk_utils import (
    estimate_tokens,
    find_block_end,
    infer_visibility,
    line_count_of,
    repository_id_for,
    resolve_chunk_dependencies,
    slice_lines,
    split_into_blocks,
    stable_chunk_id,
    content_hash,
    top_level_names,
    refine_import_locality,
)
from app.services.repository.constants import (
    CONFIG_FILE_NAMES as _CONFIG_NAMES,
    DEFAULT_SCAN_SETTINGS,
    ScanSettings,
)
from app.services.repository.detector import FrameworkDetector, LanguageDetector
from app.services.repository.exceptions import FileProcessingError, RepositoryError
from app.services.repository.models import (
    ClassMetadata,
    FunctionMetadata,
    ImportMetadata,
    Language,
    ScannedFile,
)
from app.services.repository.parser import Extraction, ParserRegistry
from app.services.repository.scanner import RepositoryScanner
from app.services.repository.utils import read_text

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Exceptions (additive — the module never raises bare Exception)
# ---------------------------------------------------------------------------


class ChunkGenerationError(RepositoryError):
    """A chunk-generation run could not be completed."""

    status_code = 422
    code = "chunk_generation_failed"


# ---------------------------------------------------------------------------
# Config & context
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ChunkerConfig:
    """Tunable, non-arbitrary limits. ``max_chunk_lines`` only decides *when* a
    symbol is split into logical blocks — the split itself is always on
    blank-line/block boundaries, never a hard cut."""

    max_chunk_lines: int = 200
    min_block_lines: int = 8
    prepend_parent_context: bool = True
    include_content: bool = True

    def merged(self, request: ChunkGenerationRequest) -> "ChunkerConfig":
        from dataclasses import replace

        changes = {}
        if request.max_chunk_lines is not None:
            changes["max_chunk_lines"] = request.max_chunk_lines
        changes["include_content"] = request.include_content
        return replace(self, **changes)


@dataclass
class FileChunkContext:
    """Everything a strategy needs to chunk one file — assembled once per file."""

    repository_id: str
    repository_name: str
    framework: str | None
    scanned: ScannedFile
    extraction: Extraction
    text_lines: list[str]
    config: ChunkerConfig

    @property
    def language(self) -> Language:
        return self.scanned.language

    @property
    def imports(self) -> list[ImportMetadata]:
        return self.extraction.imports


_HOOK_CALL_RE = re.compile(r"\b(use[A-Z][A-Za-z0-9_$]*)\s*\(")
_PY_ENUM_BASES = {"Enum", "IntEnum", "StrEnum", "Flag", "IntFlag"}
_PY_CONST_RE = re.compile(r"^(?P<name>[A-Z][A-Z0-9_]*)\s*(?::[^=]+)?=")


# ---------------------------------------------------------------------------
# Chunk assembler (shared by all strategies — DRY, single place that builds a
# fully-populated Chunk: id, hash, deps, visibility, counts).
# ---------------------------------------------------------------------------


class ChunkAssembler:
    def __init__(self, ctx: FileChunkContext) -> None:
        self._ctx = ctx

    def build(
        self,
        *,
        chunk_type: ChunkType,
        symbol_name: str,
        start_line: int,
        end_line: int,
        parent_symbol: str | None = None,
        is_async: bool = False,
        is_exported: bool = False,
        decorators: list[str] | None = None,
        context_prefix: str = "",
        part_index: int | None = None,
        part_total: int | None = None,
    ) -> Chunk:
        ctx = self._ctx
        body = slice_lines(ctx.text_lines, start_line, end_line)
        content = f"{context_prefix.rstrip()}\n\n{body}" if context_prefix else body

        signature = next((ln.strip() for ln in body.splitlines() if ln.strip()), symbol_name)
        deps = resolve_chunk_dependencies(content, ctx.imports)
        visibility = infer_visibility(
            symbol_name, ctx.language, is_exported=is_exported, declaration_line=signature
        )

        return Chunk(
            repository_id=ctx.repository_id,
            repository_name=ctx.repository_name,
            chunk_id=stable_chunk_id(
                ctx.repository_name, ctx.scanned.relative_path, symbol_name,
                chunk_type.value, start_line,
            ),
            chunk_type=chunk_type,
            language=ctx.language,
            framework=ctx.framework,
            file_path=ctx.scanned.absolute_path,
            relative_path=ctx.scanned.relative_path,
            start_line=start_line,
            end_line=end_line,
            symbol_name=symbol_name,
            parent_symbol=parent_symbol,
            signature=signature,
            is_async=is_async,
            decorators=decorators or [],
            visibility=visibility,
            imports=sorted({d.name for d in deps}),
            exports=[symbol_name] if is_exported else [],
            dependencies=deps,
            hash=content_hash(content),
            content=content if ctx.config.include_content else "",
            line_count=line_count_of(body),
            char_count=len(body),
            token_estimate=estimate_tokens(body),
            part_index=part_index,
            part_total=part_total,
        )

    def build_or_split(
        self, *, chunk_type: ChunkType, symbol_name: str, start_line: int,
        end_line: int, is_async: bool = False, is_exported: bool = False,
        decorators: list[str] | None = None, parent_symbol: str | None = None,
        context_prefix: str = "",
    ) -> list[Chunk]:
        """Emit a single chunk, or — if the symbol exceeds ``max_chunk_lines`` —
        several BLOCK chunks split on logical boundaries, linked to the parent.
        """
        span = end_line - start_line + 1
        if span <= self._ctx.config.max_chunk_lines:
            return [self.build(
                chunk_type=chunk_type, symbol_name=symbol_name, start_line=start_line,
                end_line=end_line, is_async=is_async, is_exported=is_exported,
                decorators=decorators, parent_symbol=parent_symbol, context_prefix=context_prefix,
            )]

        blocks = split_into_blocks(
            self._ctx.text_lines, start_line, end_line, self._ctx.config.min_block_lines
        )
        if len(blocks) <= 1:  # nothing to split on — keep whole rather than cut arbitrarily
            return [self.build(
                chunk_type=chunk_type, symbol_name=symbol_name, start_line=start_line,
                end_line=end_line, is_async=is_async, is_exported=is_exported,
                decorators=decorators, parent_symbol=parent_symbol, context_prefix=context_prefix,
            )]

        # Parent overview chunk (declaration + first block) plus block chunks.
        parent = self.build(
            chunk_type=chunk_type, symbol_name=symbol_name, start_line=start_line,
            end_line=blocks[0][1], is_async=is_async, is_exported=is_exported,
            decorators=decorators, parent_symbol=parent_symbol,
        )
        out = [parent]
        total = len(blocks) - 1
        for i, (bs, be) in enumerate(blocks[1:], start=1):
            block = self.build(
                chunk_type=ChunkType.BLOCK,
                symbol_name=f"{symbol_name}#block{i}",
                start_line=bs, end_line=be, parent_symbol=symbol_name,
                context_prefix=f"# section {i} of {symbol_name}",
                part_index=i, part_total=total,
            )
            block.relationships.append(
                ChunkRelationship(relation=RelationshipType.PART_OF,
                                  target_symbol=symbol_name, target_chunk_id=parent.chunk_id)
            )
            parent.relationships.append(
                ChunkRelationship(relation=RelationshipType.HAS_PART,
                                  target_symbol=block.symbol_name, target_chunk_id=block.chunk_id)
            )
            out.append(block)
        return out


# ---------------------------------------------------------------------------
# Strategy interface
# ---------------------------------------------------------------------------


class ChunkStrategy(Protocol):
    def generate(self, ctx: FileChunkContext) -> list[Chunk]: ...


# ---------------------------------------------------------------------------
# Python
# ---------------------------------------------------------------------------


class PythonChunkStrategy:
    def generate(self, ctx: FileChunkContext) -> list[Chunk]:
        asm = ChunkAssembler(ctx)
        chunks: list[Chunk] = []

        for fn in ctx.extraction.functions:
            ctype = ChunkType.ASYNC_FUNCTION if fn.is_async else ChunkType.FUNCTION
            chunks.extend(asm.build_or_split(
                chunk_type=ctype, symbol_name=fn.name, start_line=fn.line_start,
                end_line=fn.line_end, is_async=fn.is_async, is_exported=fn.is_exported,
                decorators=fn.decorators,
            ))

        for cls in ctx.extraction.classes:
            chunks.extend(self._class_chunks(ctx, asm, cls))

        chunks.extend(self._module_constants(ctx, asm, chunks))

        if not chunks:  # nothing structural — keep the file understandable whole
            chunks.extend(self._whole_file(ctx, asm))
        return chunks

    def _class_chunks(
        self, ctx: FileChunkContext, asm: ChunkAssembler, cls: ClassMetadata
    ) -> list[Chunk]:
        ctype = self._class_type(cls)
        decl_line = ctx.text_lines[cls.line_start - 1] if cls.line_start <= len(ctx.text_lines) else f"class {cls.name}:"

        if not cls.methods:
            chunk = asm.build(
                chunk_type=ctype, symbol_name=cls.name, start_line=cls.line_start,
                end_line=cls.line_end, is_exported=cls.is_exported, decorators=cls.decorators,
            )
            self._add_base_relationships(chunk, cls)
            return [chunk]

        first_method = min(m.line_start for m in cls.methods)
        header = asm.build(
            chunk_type=ctype, symbol_name=cls.name, start_line=cls.line_start,
            end_line=max(cls.line_start, first_method - 1), is_exported=cls.is_exported,
            decorators=cls.decorators,
        )
        self._add_base_relationships(header, cls)
        out = [header]

        for method in cls.methods:
            prefix = decl_line if ctx.config.prepend_parent_context else ""
            mtype = ChunkType.METHOD
            method_chunks = asm.build_or_split(
                chunk_type=mtype, symbol_name=method.name, start_line=method.line_start,
                end_line=method.line_end, is_async=method.is_async, parent_symbol=cls.name,
                decorators=method.decorators, context_prefix=prefix,
            )
            primary = method_chunks[0]
            primary.relationships.append(
                ChunkRelationship(relation=RelationshipType.METHOD_OF,
                                  target_symbol=cls.name, target_chunk_id=header.chunk_id)
            )
            header.relationships.append(
                ChunkRelationship(relation=RelationshipType.HAS_METHOD,
                                  target_symbol=method.name, target_chunk_id=primary.chunk_id)
            )
            out.extend(method_chunks)
        return out

    @staticmethod
    def _class_type(cls: ClassMetadata) -> ChunkType:
        deco = " ".join(cls.decorators).lower()
        if "dataclass" in deco:
            return ChunkType.DATACLASS
        if any(b.split("[")[0].split(".")[-1] in _PY_ENUM_BASES for b in cls.bases):
            return ChunkType.ENUM
        return ChunkType.CLASS

    @staticmethod
    def _add_base_relationships(chunk: Chunk, cls: ClassMetadata) -> None:
        for base in cls.bases:
            chunk.relationships.append(
                ChunkRelationship(relation=RelationshipType.EXTENDS, target_symbol=base)
            )

    def _module_constants(
        self, ctx: FileChunkContext, asm: ChunkAssembler, existing: list[Chunk]
    ) -> list[Chunk]:
        occupied = self._occupied_lines(ctx.extraction)
        const_lines = [
            ln for ln in range(1, len(ctx.text_lines) + 1)
            if ln not in occupied
            and not ctx.text_lines[ln - 1][:1].isspace()
            and _PY_CONST_RE.match(ctx.text_lines[ln - 1])
        ]
        chunks: list[Chunk] = []
        for start, end in self._group_adjacent(const_lines):
            chunks.append(asm.build(
                chunk_type=ChunkType.MODULE_CONSTANTS,
                symbol_name=f"constants@{start}", start_line=start, end_line=end,
                is_exported=True,
            ))
        return chunks

    @staticmethod
    def _occupied_lines(extraction: Extraction) -> set[int]:
        occupied: set[int] = set()
        for fn in extraction.functions:
            occupied.update(range(fn.line_start, fn.line_end + 1))
        for cls in extraction.classes:
            occupied.update(range(cls.line_start, cls.line_end + 1))
        return occupied

    @staticmethod
    def _group_adjacent(lines: list[int], max_gap: int = 2) -> list[tuple[int, int]]:
        if not lines:
            return []
        groups: list[tuple[int, int]] = []
        start = prev = lines[0]
        for ln in lines[1:]:
            if ln - prev <= max_gap:
                prev = ln
            else:
                groups.append((start, prev))
                start = prev = ln
        groups.append((start, prev))
        return groups

    @staticmethod
    def _whole_file(ctx: FileChunkContext, asm: ChunkAssembler) -> list[Chunk]:
        return asm.build_or_split(
            chunk_type=ChunkType.MODULE, symbol_name=ctx.scanned.name,
            start_line=1, end_line=max(1, len(ctx.text_lines)),
        )


# ---------------------------------------------------------------------------
# JavaScript / TypeScript / JSX / TSX
# ---------------------------------------------------------------------------


class JsTsChunkStrategy:
    def generate(self, ctx: FileChunkContext) -> list[Chunk]:
        asm = ChunkAssembler(ctx)
        chunks: list[Chunk] = []
        component_names = {c.name for c in ctx.extraction.components}

        for fn in ctx.extraction.functions:
            chunks.extend(self._function_chunks(ctx, asm, fn, component_names))
        for cls in ctx.extraction.classes:
            end = find_block_end(ctx.text_lines, cls.line_start)
            chunks.extend(asm.build_or_split(
                chunk_type=ChunkType.CLASS, symbol_name=cls.name,
                start_line=cls.line_start, end_line=end, is_exported=cls.is_exported,
            ))
        chunks.extend(self._symbol_chunks(ctx, asm))

        if not chunks:
            chunks.extend(PythonChunkStrategy._whole_file(ctx, asm))
        self._link_relationships(chunks)
        return chunks

    def _function_chunks(
        self, ctx: FileChunkContext, asm: ChunkAssembler, fn: FunctionMetadata,
        component_names: set[str],
    ) -> list[Chunk]:
        end = find_block_end(ctx.text_lines, fn.line_start)
        decl = ctx.text_lines[fn.line_start - 1] if fn.line_start <= len(ctx.text_lines) else ""
        ctype = self._classify(fn, decl, component_names)
        return asm.build_or_split(
            chunk_type=ctype, symbol_name=fn.name, start_line=fn.line_start,
            end_line=end, is_async=fn.is_async, is_exported=fn.is_exported,
        )

    @staticmethod
    def _classify(fn: FunctionMetadata, decl: str, component_names: set[str]) -> ChunkType:
        if fn.name in component_names:
            if fn.name.endswith(("Provider", "Context")) or "createContext" in decl:
                return ChunkType.CONTEXT_PROVIDER
            return ChunkType.COMPONENT
        if re.match(r"^use[A-Z]", fn.name):
            return ChunkType.HOOK
        if fn.is_exported:
            return ChunkType.UTILITY_FUNCTION
        return ChunkType.ASYNC_FUNCTION if fn.is_async else ChunkType.FUNCTION

    def _symbol_chunks(self, ctx: FileChunkContext, asm: ChunkAssembler) -> list[Chunk]:
        out: list[Chunk] = []
        for sym, ctype in (
            (ctx.extraction.interfaces, ChunkType.INTERFACE),
            (ctx.extraction.types, ChunkType.TYPE_ALIAS),
            (ctx.extraction.enums, ChunkType.ENUM),
        ):
            for s in sym:
                end = find_block_end(ctx.text_lines, s.line)
                out.append(asm.build(
                    chunk_type=ctype, symbol_name=s.name, start_line=s.line,
                    end_line=end, is_exported=s.is_exported,
                ))
        return out

    @staticmethod
    def _link_relationships(chunks: list[Chunk]) -> None:
        """Resolve in-file component→hook/type links to concrete chunk ids."""
        by_symbol = {c.symbol_name: c.chunk_id for c in chunks}
        hook_names = {c.symbol_name for c in chunks if c.chunk_type == ChunkType.HOOK.value}
        type_names = {
            c.symbol_name for c in chunks
            if c.chunk_type in (ChunkType.INTERFACE.value, ChunkType.TYPE_ALIAS.value, ChunkType.ENUM.value)
        }
        for chunk in chunks:
            if chunk.chunk_type not in (ChunkType.COMPONENT.value, ChunkType.CONTEXT_PROVIDER.value):
                continue
            tokens = set(re.findall(r"[A-Za-z_$][A-Za-z0-9_$]*", chunk.content or chunk.signature or ""))
            for hook in _HOOK_CALL_RE.findall(chunk.content or ""):
                if hook != chunk.symbol_name:
                    chunk.relationships.append(ChunkRelationship(
                        relation=RelationshipType.USES_HOOK, target_symbol=hook,
                        target_chunk_id=by_symbol.get(hook) if hook in hook_names else None,
                    ))
            for type_name in type_names & tokens:
                chunk.relationships.append(ChunkRelationship(
                    relation=RelationshipType.USES_TYPE, target_symbol=type_name,
                    target_chunk_id=by_symbol.get(type_name),
                ))


# ---------------------------------------------------------------------------
# C-family (Java / Go / Rust / C#)
# ---------------------------------------------------------------------------


class CFamilyChunkStrategy:
    _KEYWORD_TYPE = {
        "interface": ChunkType.INTERFACE, "enum": ChunkType.ENUM,
        "record": ChunkType.RECORD, "struct": ChunkType.STRUCT, "trait": ChunkType.TRAIT,
    }

    def generate(self, ctx: FileChunkContext) -> list[Chunk]:
        asm = ChunkAssembler(ctx)
        chunks: list[Chunk] = []
        class_spans: list[tuple[str, int, int, str]] = []  # name, start, end, id

        for cls in ctx.extraction.classes:
            end = find_block_end(ctx.text_lines, cls.line_start)
            decl = ctx.text_lines[cls.line_start - 1] if cls.line_start <= len(ctx.text_lines) else ""
            ctype = self._class_type(decl)
            chunk = asm.build(
                chunk_type=ctype, symbol_name=cls.name, start_line=cls.line_start,
                end_line=end, is_exported=cls.is_exported,
            )
            chunks.append(chunk)
            class_spans.append((cls.name, cls.line_start, end, chunk.chunk_id))

        for fn in ctx.extraction.functions:
            chunks.extend(self._function_chunks(ctx, asm, fn, class_spans))

        if not chunks:
            chunks.extend(PythonChunkStrategy._whole_file(ctx, asm))
        return chunks

    def _function_chunks(
        self, ctx: FileChunkContext, asm: ChunkAssembler, fn: FunctionMetadata,
        class_spans: list[tuple[str, int, int, str]],
    ) -> list[Chunk]:
        end = find_block_end(ctx.text_lines, fn.line_start)
        owner = next((c for c in class_spans if c[1] <= fn.line_start <= c[2]), None)
        if owner:
            decl_line = ctx.text_lines[owner[1] - 1] if owner[1] <= len(ctx.text_lines) else ""
            prefix = decl_line if ctx.config.prepend_parent_context else ""
            produced = asm.build_or_split(
                chunk_type=ChunkType.METHOD, symbol_name=fn.name, start_line=fn.line_start,
                end_line=end, is_async=fn.is_async, parent_symbol=owner[0], context_prefix=prefix,
            )
            produced[0].relationships.append(ChunkRelationship(
                relation=RelationshipType.METHOD_OF, target_symbol=owner[0], target_chunk_id=owner[3]
            ))
            return produced
        ctype = ChunkType.ASYNC_FUNCTION if fn.is_async else ChunkType.FUNCTION
        return asm.build_or_split(
            chunk_type=ctype, symbol_name=fn.name, start_line=fn.line_start,
            end_line=end, is_async=fn.is_async, is_exported=fn.is_exported,
        )

    def _class_type(self, declaration: str) -> ChunkType:
        decl = declaration.lower()
        for keyword, ctype in self._KEYWORD_TYPE.items():
            if re.search(rf"\b{keyword}\b", decl):
                return ctype
        return ChunkType.CLASS


# ---------------------------------------------------------------------------
# Single-file (config / data / markup / documentation)
# ---------------------------------------------------------------------------


class SingleFileChunkStrategy:
    _WHOLE_TYPE = {
        Language.MARKDOWN: ChunkType.DOCUMENT,
        Language.CSS: ChunkType.STYLE, Language.SCSS: ChunkType.STYLE,
        Language.HTML: ChunkType.MARKUP, Language.XML: ChunkType.MARKUP,
        Language.VUE: ChunkType.MARKUP, Language.SVELTE: ChunkType.MARKUP,
        Language.JSON: ChunkType.DATA, Language.YAML: ChunkType.DATA, Language.TOML: ChunkType.DATA,
    }

    def generate(self, ctx: FileChunkContext) -> list[Chunk]:
        asm = ChunkAssembler(ctx)
        end = max(1, len(ctx.text_lines))
        is_config = ctx.scanned.name.lower() in _CONFIG_NAMES

        if is_config:  # config files are always a single chunk (per spec)
            return [asm.build(
                chunk_type=ChunkType.CONFIG_FILE, symbol_name=ctx.scanned.name,
                start_line=1, end_line=end, is_exported=False,
            )]

        ctype = self._WHOLE_TYPE.get(ctx.language, ChunkType.MODULE)
        # Docs/markup may be large — split on logical boundaries; data stays whole.
        if ctype in (ChunkType.DOCUMENT, ChunkType.MARKUP):
            return asm.build_or_split(
                chunk_type=ctype, symbol_name=ctx.scanned.name, start_line=1, end_line=end,
            )
        return [asm.build(
            chunk_type=ctype, symbol_name=ctx.scanned.name, start_line=1, end_line=end,
        )]


# ---------------------------------------------------------------------------
# Strategy registry
# ---------------------------------------------------------------------------


class ChunkStrategyRegistry:
    def __init__(self) -> None:
        py = PythonChunkStrategy()
        js = JsTsChunkStrategy()
        cfam = CFamilyChunkStrategy()
        self._single = SingleFileChunkStrategy()
        self._by_language: dict[Language, ChunkStrategy] = {
            Language.PYTHON: py,
            Language.JAVASCRIPT: js, Language.JSX: js,
            Language.TYPESCRIPT: js, Language.TSX: js,
            Language.JAVA: cfam, Language.GO: cfam,
            Language.RUST: cfam, Language.CSHARP: cfam,
        }

    def for_file(self, scanned: ScannedFile) -> ChunkStrategy:
        if scanned.name.lower() in _CONFIG_NAMES:
            return self._single
        return self._by_language.get(scanned.language, self._single)


# ---------------------------------------------------------------------------
# Statistics accumulator (streaming — never holds all chunks to compute stats)
# ---------------------------------------------------------------------------


class _StatisticsAccumulator:
    def __init__(self) -> None:
        self._stats = ChunkStatistics()
        self._files_seen: set[str] = set()
        self._files_with_chunks: set[str] = set()
        self._total_chars = 0
        self._total_lines = 0

    def note_file(self, relative_path: str) -> None:
        self._files_seen.add(relative_path)

    def add(self, chunk: Chunk) -> None:
        s = self._stats
        s.total_chunks += 1
        self._files_with_chunks.add(chunk.relative_path)
        s.chunks_per_file[chunk.relative_path] = s.chunks_per_file.get(chunk.relative_path, 0) + 1
        lang = str(chunk.language)
        s.chunks_per_language[lang] = s.chunks_per_language.get(lang, 0) + 1
        ctype = str(chunk.chunk_type)
        s.chunks_per_type[ctype] = s.chunks_per_type.get(ctype, 0) + 1
        if chunk.framework:
            s.chunks_per_framework[chunk.framework] = s.chunks_per_framework.get(chunk.framework, 0) + 1

        self._total_chars += chunk.char_count
        self._total_lines += chunk.line_count
        ref = ChunkSizeRef(
            chunk_id=chunk.chunk_id, symbol_name=chunk.symbol_name,
            char_count=chunk.char_count, line_count=chunk.line_count,
        )
        if s.largest_chunk is None or chunk.char_count > s.largest_chunk.char_count:
            s.largest_chunk = ref
        if s.smallest_chunk is None or chunk.char_count < s.smallest_chunk.char_count:
            s.smallest_chunk = ref

    def finalize(self) -> ChunkStatistics:
        s = self._stats
        s.total_files = len(self._files_seen)
        s.files_with_chunks = len(self._files_with_chunks)
        if s.total_chunks:
            s.average_chunk_chars = round(self._total_chars / s.total_chunks, 2)
            s.average_chunk_lines = round(self._total_lines / s.total_chunks, 2)
        return s


# ---------------------------------------------------------------------------
# Generator (orchestrator)
# ---------------------------------------------------------------------------


class ChunkGenerator:
    """Streams :class:`Chunk` records for a repository. Collaborators injected."""

    def __init__(
        self,
        scan_settings: ScanSettings = DEFAULT_SCAN_SETTINGS,
        parser_registry: ParserRegistry | None = None,
        strategies: ChunkStrategyRegistry | None = None,
        framework_detector: FrameworkDetector | None = None,
        language_detector: LanguageDetector | None = None,
        config: ChunkerConfig = ChunkerConfig(),
    ) -> None:
        self._scan_settings = scan_settings
        self._parsers = parser_registry or ParserRegistry()
        self._strategies = strategies or ChunkStrategyRegistry()
        self._frameworks = framework_detector or FrameworkDetector()
        self._languages = language_detector or LanguageDetector()
        self._config = config

    # -- streaming API (future embedding/upsert consumes this directly) ------

    def iter_chunks(
        self, root: str, scanned: list[ScannedFile], *, repository_id: str,
        repository_name: str, framework: str | None, config: ChunkerConfig,
        accumulator: _StatisticsAccumulator | None = None,
    ) -> Iterator[Chunk]:
        internal_names = top_level_names(scanned)
        for entry in scanned:
            if accumulator is not None:
                accumulator.note_file(entry.relative_path)
            try:
                text = read_text(entry.absolute_path)
            except FileProcessingError as exc:
                logger.warning("Skipping unreadable file %s: %s", entry.relative_path, exc.detail)
                continue

            if not text.strip():  # empty/whitespace-only file → nothing to chunk
                continue

            extraction = self._parsers.parse(entry, text)
            refine_import_locality(extraction.imports, internal_names)
            ctx = FileChunkContext(
                repository_id=repository_id, repository_name=repository_name,
                framework=framework, scanned=entry, extraction=extraction,
                text_lines=text.split("\n"), config=config,
            )
            produced = self._strategies.for_file(entry).generate(ctx)
            for chunk in produced:
                yield chunk

    # -- request/response API ------------------------------------------------

    def generate(self, request: ChunkGenerationRequest) -> ChunkGenerationResponse:
        started = time.perf_counter()
        run_settings = self._scan_settings.with_overrides(
            max_file_size_bytes=request.max_file_size_bytes
        )
        config = self._config.merged(request)
        scanner = RepositoryScanner(run_settings)

        root = scanner.validate_root(request.repository_path)
        scanned, _tally = scanner.scan(root)
        if not scanned:
            raise ChunkGenerationError("No supported, readable files were found.")

        import os

        repository_name = os.path.basename(root.rstrip(os.sep)) or root
        repository_id = repository_id_for(root)
        detections = self._frameworks.detect(root)
        primary_framework = detections[0].name if detections else None
        primary_language, secondary = self._languages.primary_and_secondary(scanned)

        accumulator = _StatisticsAccumulator()
        chunks: list[Chunk] = []
        for chunk in self.iter_chunks(
            root, scanned, repository_id=repository_id, repository_name=repository_name,
            framework=primary_framework, config=config, accumulator=accumulator,
        ):
            accumulator.add(chunk)
            chunks.append(chunk)

        statistics = accumulator.finalize()
        duration_ms = (time.perf_counter() - started) * 1000.0

        logger.info(
            "Chunk generation complete: %s | %d chunks from %d files | framework=%s | %.1fms",
            repository_name, statistics.total_chunks, statistics.files_with_chunks,
            primary_framework or "none", duration_ms,
        )

        summary = ChunkSummary(
            repository_id=repository_id, repository_name=repository_name, root_path=root,
            primary_language=primary_language, primary_framework=primary_framework,
            languages=[primary_language, *secondary] if primary_language else [],
            frameworks=[d.name for d in detections],
            total_files=statistics.total_files, total_chunks=statistics.total_chunks,
            generated_at=datetime.now(timezone.utc), duration_ms=round(duration_ms, 2),
        )
        return ChunkGenerationResponse(summary=summary, statistics=statistics, chunks=chunks)
