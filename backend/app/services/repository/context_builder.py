"""Context Builder.

Takes ranked :class:`RetrievedChunk` results and organises them into a clean,
token-budgeted :class:`RepositoryContext`:

  dedupe → classify into sections → prioritise → estimate tokens →
  budget (compress, then trim least-important) → preserve metadata

Pure and deterministic; it performs no retrieval and no I/O, so it is trivially
testable and reusable by chat, prompting, and editing alike.
"""

from __future__ import annotations

import logging

from app.services.repository.chunk_utils import estimate_tokens
from app.services.repository.context_models import (
    CONTEXT_WINDOWS,
    DEFAULT_WINDOW_TOKENS,
    ContextChunk,
    ContextRelationship,
    ContextSection,
    ContextStatistics,
    RepositoryContext,
)
from app.services.repository.retrieval_models import RetrievalSource, RetrievedChunk

logger = logging.getLogger(__name__)

#: Section priority for budgeting — earlier sections are kept longer under
#: pressure and trimmed last.
_SECTION_PRIORITY: list[ContextSection] = [
    ContextSection.PRIMARY,
    ContextSection.SUPPORTING,
    ContextSection.CONFIGURATION,
    ContextSection.UTILITIES,
    ContextSection.ADDITIONAL,
]

_UTILITY_TYPES = {"utility_function", "module_constants", "module"}
_CONFIG_TYPES = {"config_file"}


class ContextBuilderConfig:
    """Compression / budgeting knobs (constructor args, not env — the caller
    passes the window)."""

    def __init__(
        self,
        scaffold_reserve_tokens: int = 700,
        compress_over_tokens: int = 700,
        compress_head_lines: int = 24,
        compress_tail_lines: int = 8,
    ) -> None:
        self.scaffold_reserve_tokens = scaffold_reserve_tokens
        self.compress_over_tokens = compress_over_tokens
        self.compress_head_lines = compress_head_lines
        self.compress_tail_lines = compress_tail_lines


class ContextBuilder:
    def __init__(self, config: ContextBuilderConfig | None = None) -> None:
        self._config = config or ContextBuilderConfig()

    # -- public API ---------------------------------------------------------

    def build(
        self,
        *,
        repository_id: str,
        repository_name: str,
        query: str,
        chunks: list[RetrievedChunk],
        context_window: str | int = DEFAULT_WINDOW_TOKENS,
        response_reserve_ratio: float = 0.35,
    ) -> RepositoryContext:
        window_tokens = self._resolve_window(context_window)
        budget = max(
            256,
            int(window_tokens * (1.0 - response_reserve_ratio)) - self._config.scaffold_reserve_tokens,
        )

        deduped, duplicates_removed = self._dedupe(chunks)
        candidates = [self._to_context_chunk(c) for c in deduped]
        ordered = self._prioritise(candidates)

        included, trimmed, compressed = self._apply_budget(ordered, budget)
        context = self._assemble(
            repository_id, repository_name, query, included, window_tokens, budget,
            trimmed, compressed, duplicates_removed,
        )
        logger.info(
            "Context built: repo=%s window=%d budget=%d used=%d included=%d trimmed=%d compressed=%d",
            repository_name, window_tokens, budget, context.statistics.used_tokens,
            context.statistics.included_chunks, len(trimmed), compressed,
        )
        return context

    # -- steps --------------------------------------------------------------

    @staticmethod
    def _resolve_window(context_window: str | int) -> int:
        if isinstance(context_window, int):
            return max(1024, context_window)
        return CONTEXT_WINDOWS.get(context_window.lower().strip(), DEFAULT_WINDOW_TOKENS)

    @staticmethod
    def _dedupe(chunks: list[RetrievedChunk]) -> tuple[list[RetrievedChunk], int]:
        """Remove duplicate chunk_ids and identical (path, span) content, keeping
        the highest-scoring occurrence."""
        best: dict[str, RetrievedChunk] = {}
        for chunk in chunks:
            key = chunk.chunk_id or f"{chunk.relative_path}:{chunk.start_line}:{chunk.symbol}"
            existing = best.get(key)
            if existing is None or chunk.rank_score > existing.rank_score:
                best[key] = chunk
        removed = len(chunks) - len(best)
        return list(best.values()), removed

    def _to_context_chunk(self, chunk: RetrievedChunk) -> ContextChunk:
        return ContextChunk(
            chunk_id=chunk.chunk_id,
            section=self._section_for(chunk),
            symbol=chunk.symbol,
            parent_symbol=chunk.parent_symbol,
            chunk_type=chunk.chunk_type,
            language=chunk.language,
            framework=chunk.framework,
            relative_path=chunk.relative_path,
            start_line=chunk.start_line,
            end_line=chunk.end_line,
            visibility=chunk.visibility,
            score=chunk.rank_score or chunk.score,
            summary=chunk.summary,
            content=chunk.content,
            tokens=estimate_tokens(self._render(chunk.relative_path, chunk.symbol, chunk.content)),
            dependencies=[d.name for d in chunk.dependencies if not d.is_external],
            relationships=[
                ContextRelationship(relation=r.relation, target_symbol=r.target_symbol,
                                    target_chunk_id=r.target_chunk_id)
                for r in chunk.relationships
            ],
        )

    @staticmethod
    def _section_for(chunk: RetrievedChunk) -> ContextSection:
        if chunk.chunk_type in _CONFIG_TYPES:
            return ContextSection.CONFIGURATION
        if chunk.source is RetrievalSource.DEPENDENCY_EXPANSION or chunk.depth > 0:
            return ContextSection.SUPPORTING
        if chunk.chunk_type in _UTILITY_TYPES:
            return ContextSection.UTILITIES
        if chunk.depth == 0 and chunk.source is RetrievalSource.SEMANTIC:
            return ContextSection.PRIMARY
        return ContextSection.ADDITIONAL

    @staticmethod
    def _prioritise(chunks: list[ContextChunk]) -> list[ContextChunk]:
        rank = {section: i for i, section in enumerate(_SECTION_PRIORITY)}
        return sorted(chunks, key=lambda c: (rank.get(c.section, 99), -c.score))

    def _apply_budget(
        self, ordered: list[ContextChunk], budget: int
    ) -> tuple[list[ContextChunk], list[ContextChunk], int]:
        used = 0
        included: list[ContextChunk] = []
        trimmed: list[ContextChunk] = []
        compressed_count = 0
        for chunk in ordered:
            if used + chunk.tokens <= budget:
                included.append(chunk)
                used += chunk.tokens
                continue
            # Try compression before dropping.
            compact = self._compress(chunk)
            if compact is not None and used + compact.tokens <= budget:
                included.append(compact)
                used += compact.tokens
                compressed_count += 1
            else:
                trimmed.append(chunk)
        return included, trimmed, compressed_count

    def _compress(self, chunk: ContextChunk) -> ContextChunk | None:
        if chunk.tokens <= self._config.compress_over_tokens:
            return None
        lines = chunk.content.split("\n")
        head = self._config.compress_head_lines
        tail = self._config.compress_tail_lines
        if len(lines) <= head + tail:
            return None
        omitted = len(lines) - head - tail
        body = "\n".join(
            [*lines[:head], f"    // ... {omitted} lines omitted for brevity ...", *lines[-tail:]]
        )
        clone = chunk.model_copy(update={
            "content": body,
            "compressed": True,
            "tokens": estimate_tokens(self._render(chunk.relative_path, chunk.symbol, body)),
        })
        return clone

    @staticmethod
    def _render(relative_path: str, symbol: str, content: str) -> str:
        return f"// {relative_path} :: {symbol}\n{content}"

    def _assemble(
        self, repository_id: str, repository_name: str, query: str,
        included: list[ContextChunk], window_tokens: int, budget: int,
        trimmed: list[ContextChunk], compressed_count: int, duplicates_removed: int,
    ) -> RepositoryContext:
        buckets: dict[ContextSection, list[ContextChunk]] = {s: [] for s in ContextSection}
        for chunk in included:
            buckets[chunk.section].append(chunk)

        stats = ContextStatistics(
            window_tokens=window_tokens,
            budget_tokens=budget,
            used_tokens=sum(c.tokens for c in included),
            included_chunks=len(included),
            trimmed_chunks=len(trimmed),
            compressed_chunks=compressed_count,
            duplicate_chunks_removed=duplicates_removed,
            trimmed_symbols=[c.symbol for c in trimmed],
        )
        return RepositoryContext(
            repository_id=repository_id,
            repository_name=repository_name,
            query=query,
            summary=self._summary(repository_name, included),
            primary=buckets[ContextSection.PRIMARY],
            supporting_dependencies=buckets[ContextSection.SUPPORTING],
            configuration=buckets[ContextSection.CONFIGURATION],
            utilities=buckets[ContextSection.UTILITIES],
            additional_references=buckets[ContextSection.ADDITIONAL],
            statistics=stats,
        )

    @staticmethod
    def _summary(repository_name: str, chunks: list[ContextChunk]) -> str:
        if not chunks:
            return f"Repository '{repository_name}'."
        languages = sorted({c.language for c in chunks if c.language})
        frameworks = sorted({c.framework for c in chunks if c.framework})
        files = sorted({c.relative_path for c in chunks})
        parts = [f"Repository '{repository_name}'"]
        if frameworks:
            parts.append(f"framework: {', '.join(frameworks)}")
        if languages:
            parts.append(f"languages: {', '.join(languages)}")
        parts.append(f"{len(files)} relevant file(s) in context")
        return "; ".join(parts) + "."
