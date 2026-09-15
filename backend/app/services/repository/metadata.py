"""Repository indexer — the aggregation service.

Orchestrates the pipeline:

    scan → detect frameworks/languages → parse each file → resolve
    dependencies → compute statistics → assemble response.

This is the single entry point the FastAPI router depends on. Collaborators
(scanner, detector, parser registry) are injected, so the orchestration is
unit-testable and each stage is independently replaceable — the seam future
phases (Chunk Generator, Embedding Engine, Dependency Graph) build on.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone

from app.services.repository.constants import (
    DEFAULT_SCAN_SETTINGS,
    PARSEABLE_LANGUAGES,
    ScanSettings,
)
from app.services.repository.detector import FrameworkDetector, LanguageDetector
from app.services.repository.exceptions import (
    EmptyRepositoryError,
    FileProcessingError,
)
from app.services.repository.models import (
    DependencyMetadata,
    FileMetadata,
    LargestFile,
    Language,
    RepositoryIndexRequest,
    RepositoryIndexResponse,
    RepositoryMetadata,
    RepositoryStatistics,
    ScannedFile,
)
from app.services.repository.parser import Extraction, ParserRegistry
from app.services.repository.scanner import RepositoryScanner, ScanTally
from app.services.repository.utils import (
    categorize,
    content_hash,
    count_lines,
    human_readable_size,
    is_config_file,
    read_text,
    top_segment,
)

logger = logging.getLogger(__name__)


class _InternalResolver:
    """Classifies an import specifier as internal (in-repo) or external.

    Internal = a relative import, or one whose first segment matches a
    top-level package/module/directory present in the repository (covers
    monorepo path aliases and Python packages).
    """

    def __init__(self, scanned: list[ScannedFile]) -> None:
        self._names = self._top_level_names(scanned)

    @staticmethod
    def _top_level_names(scanned: list[ScannedFile]) -> set[str]:
        names: set[str] = set()
        for f in scanned:
            head, _, tail = f.relative_path.partition("/")
            if tail:  # nested → 'head' is a top-level directory
                names.add(head)
            else:  # top-level file → its stem is an importable module name
                names.add(f.name.rsplit(".", 1)[0])
        return names

    def is_internal(self, module: str, is_relative: bool) -> bool:
        if is_relative:
            return True
        return top_segment(module) in self._names


class RepositoryIndexer:
    """Builds a :class:`RepositoryIndexResponse` for a repository path."""

    def __init__(
        self,
        scanner: RepositoryScanner | None = None,
        framework_detector: FrameworkDetector | None = None,
        language_detector: LanguageDetector | None = None,
        parser_registry: ParserRegistry | None = None,
        settings: ScanSettings = DEFAULT_SCAN_SETTINGS,
    ) -> None:
        self._settings = settings
        self._scanner = scanner or RepositoryScanner(settings)
        self._frameworks = framework_detector or FrameworkDetector()
        self._languages = language_detector or LanguageDetector()
        self._parsers = parser_registry or ParserRegistry()

    # -- public API ---------------------------------------------------------

    def index(self, request: RepositoryIndexRequest) -> RepositoryIndexResponse:
        started = time.perf_counter()
        run_settings = self._settings.with_overrides(
            max_file_size_bytes=request.max_file_size_bytes
        )
        scanner = RepositoryScanner(run_settings)

        root = scanner.validate_root(request.repository_path)
        scanned, tally = scanner.scan(root)
        if not scanned:
            raise EmptyRepositoryError("No supported, readable files were found.")

        frameworks = self._frameworks.detect(root)
        primary_language, secondary_languages = self._languages.primary_and_secondary(scanned)

        resolver = _InternalResolver(scanned)
        files = self._parse_all(scanned, resolver)

        duration_ms = (time.perf_counter() - started) * 1000.0
        repository = self._repository_metadata(
            root, frameworks, primary_language, secondary_languages, duration_ms
        )
        statistics = self._statistics(
            scanned, files, tally, primary_language, secondary_languages
        )

        logger.info(
            "Repository indexed: %s | %d files parsed, %d failed | framework=%s | %.1fms",
            repository.name, statistics.parsed_files, statistics.failed_files,
            repository.primary_framework.name if repository.primary_framework else "none",
            duration_ms,
        )

        return RepositoryIndexResponse(
            repository=repository,
            framework=frameworks[0] if frameworks else None,
            statistics=statistics,
            files=files if request.include_files else [],
        )

    # -- parsing ------------------------------------------------------------

    def _parse_all(
        self, scanned: list[ScannedFile], resolver: _InternalResolver
    ) -> list[FileMetadata]:
        files: list[FileMetadata] = []
        for entry in scanned:
            files.append(self._parse_one(entry, resolver))
        logger.info("Files parsed: %d", len(files))
        return files

    def _parse_one(self, entry: ScannedFile, resolver: _InternalResolver) -> FileMetadata:
        meta = self._base_metadata(entry)
        try:
            text = read_text(entry.absolute_path)
        except FileProcessingError as exc:
            meta.parse_error = exc.detail
            logger.warning("Skipping unreadable file %s: %s", entry.relative_path, exc.detail)
            return meta

        meta.line_count = count_lines(text)
        meta.content_hash = content_hash(text)

        extraction = self._parsers.parse(entry, text)
        self._apply_extraction(meta, extraction, resolver)
        return meta

    @staticmethod
    def _base_metadata(entry: ScannedFile) -> FileMetadata:
        language = entry.language
        return FileMetadata(
            relative_path=entry.relative_path,
            absolute_path=entry.absolute_path,
            name=entry.name,
            extension=entry.extension,
            language=language,
            category=categorize(language, entry.name),
            is_config=is_config_file(entry.name),
            size_bytes=entry.size_bytes,
            size_human=human_readable_size(entry.size_bytes),
        )

    def _apply_extraction(
        self, meta: FileMetadata, extraction: Extraction, resolver: _InternalResolver
    ) -> None:
        meta.parse_error = extraction.error
        meta.imports = extraction.imports
        meta.exports = extraction.exports
        meta.functions = extraction.functions
        meta.classes = extraction.classes
        meta.components = extraction.components
        meta.hooks = extraction.hooks
        meta.interfaces = extraction.interfaces
        meta.types = extraction.types
        meta.enums = extraction.enums
        meta.decorators = extraction.decorators
        meta.async_functions = extraction.async_functions
        meta.dependencies = self._dependencies(extraction, resolver)

    @staticmethod
    def _dependencies(extraction: Extraction, resolver: _InternalResolver) -> DependencyMetadata:
        deps = DependencyMetadata()
        for imp in extraction.imports:
            internal = resolver.is_internal(imp.module, imp.is_relative)
            imp.is_external = not internal
            if imp.is_relative:
                deps.relative.append(imp.module)
            if internal:
                deps.internal.append(imp.module)
            else:
                deps.external.append(top_segment(imp.module))
        deps.internal = sorted(set(deps.internal))
        deps.external = sorted(set(deps.external))
        deps.relative = sorted(set(deps.relative))
        return deps

    # -- assembly -----------------------------------------------------------

    def _repository_metadata(
        self,
        root: str,
        frameworks: list,
        primary_language: Language | None,
        secondary_languages: list[Language],
        duration_ms: float,
    ) -> RepositoryMetadata:
        import os

        languages = [primary_language, *secondary_languages] if primary_language else []
        return RepositoryMetadata(
            name=os.path.basename(root.rstrip(os.sep)) or root,
            root_path=root,
            primary_framework=frameworks[0] if frameworks else None,
            frameworks=frameworks,
            primary_language=primary_language,
            languages=languages,
            scanned_at=datetime.now(timezone.utc),
            duration_ms=round(duration_ms, 2),
        )

    def _statistics(
        self,
        scanned: list[ScannedFile],
        files: list[FileMetadata],
        tally: ScanTally,
        primary_language: Language | None,
        secondary_languages: list[Language],
    ) -> RepositoryStatistics:
        breakdown: dict[str, int] = {}
        for f in files:
            breakdown[f.language.value] = breakdown.get(f.language.value, 0) + 1

        supported = sum(1 for f in files if f.language is not Language.UNKNOWN)
        failed = sum(1 for f in files if f.parse_error)
        parseable = sum(1 for f in files if f.language in PARSEABLE_LANGUAGES and not f.parse_error)
        total_size = sum(f.size_bytes for f in files)
        total_lines = sum(f.line_count for f in files)
        largest = max(files, key=lambda f: f.size_bytes, default=None)

        return RepositoryStatistics(
            total_files=len(files),
            supported_files=supported,
            parsed_files=parseable,
            failed_files=failed,
            ignored_files=tally.ignored_files + tally.oversized,
            directory_count=len(tally.directories),
            primary_language=primary_language,
            secondary_languages=secondary_languages,
            language_breakdown=breakdown,
            total_size_bytes=total_size,
            total_lines=total_lines,
            average_file_size_bytes=round(total_size / len(files), 2) if files else 0.0,
            largest_file=(
                LargestFile(
                    relative_path=largest.relative_path,
                    size_bytes=largest.size_bytes,
                    size_human=largest.size_human,
                )
                if largest
                else None
            ),
        )
