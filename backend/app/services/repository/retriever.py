"""Repository Retriever — the retrieval orchestrator.

    query → embed (once) → vector search → metadata filter →
    dependency expansion (BFS, loop-safe) → rerank → ranked chunks

Reuses the existing ``EmbeddingService`` (query embedding) and ``VectorStore``
(search/fetch) — it never touches ChromaDB directly and never re-embeds indexed
chunks. Every collaborator is injected, so the query processor, store, and
reranker are all swappable; this class is the retrieval layer future modules
(Context Builder, Conversation Memory, Hybrid Search, Agentic Workflows)
consume without modification.
"""

from __future__ import annotations

import json
import logging
import time

from app.services.repository.embedding_config import EmbeddingSettings, embedding_settings
from app.services.repository.exceptions import RepositoryError
from app.services.repository.query_processor import ProcessedQuery, QueryProcessor
from app.services.repository.reranker import Reranker
from app.services.repository.retrieval_config import RetrievalSettings, retrieval_settings
from app.services.repository.retrieval_models import (
    ChunkDependencyInfo,
    RelationshipEdge,
    RetrievalSource,
    RetrievalStatistics,
    RetrievedChunk,
    RetrieveRequest,
    RetrieveResponse,
)
from app.services.repository.vector_store import VectorMatch, VectorStore

logger = logging.getLogger(__name__)

_SUMMARY_MAX = 160


class _ResolvedOptions:
    """Per-request options merged over the configured defaults."""

    __slots__ = ("top_k", "threshold", "expansion", "max_depth", "max_chunks", "fetch_k")

    def __init__(self, request: RetrieveRequest, config: RetrievalSettings) -> None:
        self.top_k = request.top_k or config.top_k
        self.threshold = (
            request.similarity_threshold
            if request.similarity_threshold is not None
            else config.similarity_threshold
        )
        self.expansion = (
            request.dependency_expansion
            if request.dependency_expansion is not None
            else config.enable_dependency_expansion
        )
        self.max_depth = (
            request.max_expansion_depth
            if request.max_expansion_depth is not None
            else config.max_expansion_depth
        )
        self.max_chunks = config.max_retrieved_chunks
        self.fetch_k = min(config.max_retrieved_chunks, max(self.top_k, self.top_k * config.fetch_multiplier))


class RepositoryRetriever:
    def __init__(
        self,
        query_processor: QueryProcessor,
        vector_store: VectorStore,
        reranker: Reranker,
        config: RetrievalSettings = retrieval_settings,
        embedding_config: EmbeddingSettings = embedding_settings,
    ) -> None:
        self._processor = query_processor
        self._store = vector_store
        self._reranker = reranker
        self._config = config
        self._embedding_config = embedding_config

    # -- public API ---------------------------------------------------------

    def retrieve(self, request: RetrieveRequest) -> RetrieveResponse:
        started = time.perf_counter()
        options = _ResolvedOptions(request, self._config)
        collection = self._embedding_config.collection_name(request.repository_id)
        stats = RetrievalStatistics()

        processed = self._processor.process(request.query, collection, request.repository_id)
        stats.embedding_ms = round(processed.embedding_ms, 2)

        direct = self._semantic_search(collection, processed, request, options, stats)
        expanded = self._expand_dependencies(collection, direct, options, stats)

        all_results = direct + expanded
        self._attach_relationships(all_results)

        began = time.perf_counter()
        ordered = self._reranker.rerank(processed, all_results)[: options.max_chunks]
        stats.rerank_ms = round((time.perf_counter() - began) * 1000.0, 2)

        stats.chunks_retrieved = len(direct)
        stats.chunks_expanded = len(expanded)
        stats.final_result_count = len(ordered)
        stats.total_ms = round((time.perf_counter() - started) * 1000.0, 2)

        logger.info(
            "Retrieval done: repo=%s direct=%d expanded=%d final=%d | embed=%.0f search=%.0f "
            "expand=%.0f rerank=%.0f total=%.0fms",
            request.repository_id, stats.chunks_retrieved, stats.chunks_expanded,
            stats.final_result_count, stats.embedding_ms, stats.vector_search_ms,
            stats.expansion_ms, stats.rerank_ms, stats.total_ms,
        )

        return RetrieveResponse(
            repository_id=request.repository_id,
            query=processed.normalized,
            collection_name=collection,
            embedding_model=self._processor.embedding_model,
            results=ordered,
            expanded_dependencies=sorted({c.symbol for c in expanded}),
            statistics=stats,
        )

    # -- semantic search ----------------------------------------------------

    def _semantic_search(
        self, collection: str, processed: ProcessedQuery, request: RetrieveRequest,
        options: _ResolvedOptions, stats: RetrievalStatistics,
    ) -> list[RetrievedChunk]:
        where = self._build_where(request)
        began = time.perf_counter()
        matches = self._store.query(collection, processed.embedding, options.fetch_k, where)
        stats.vector_search_ms = round((time.perf_counter() - began) * 1000.0, 2)
        stats.vector_queries += 1

        prefix = request.filters.path_prefix if request.filters else None
        chunks: list[RetrievedChunk] = []
        for match in matches:
            if match.score < options.threshold:
                continue
            if prefix and not str(match.metadata.get("relative_path", "")).startswith(prefix):
                continue
            chunks.append(self._to_chunk(match, RetrievalSource.SEMANTIC, depth=0))
            if len(chunks) >= options.top_k:
                break
        return chunks

    def _build_where(self, request: RetrieveRequest) -> dict | None:
        f = request.filters
        if not f:
            return None
        clauses: list[dict] = []
        if f.language:
            clauses.append({"language": f.language})
        if f.framework:
            clauses.append({"framework": f.framework})
        if f.chunk_type:
            clauses.append({"chunk_type": f.chunk_type})
        if f.chunk_types:
            clauses.append({"chunk_type": {"$in": f.chunk_types}})
        if f.symbol:
            clauses.append({"symbol": f.symbol})
        if f.visibility:
            clauses.append({"visibility": f.visibility})
        if f.relative_path:
            clauses.append({"relative_path": f.relative_path})
        if not clauses:
            return None
        return clauses[0] if len(clauses) == 1 else {"$and": clauses}

    # -- dependency expansion (BFS, loop-safe) ------------------------------

    def _expand_dependencies(
        self, collection: str, direct: list[RetrievedChunk],
        options: _ResolvedOptions, stats: RetrievalStatistics,
    ) -> list[RetrievedChunk]:
        if not options.expansion or options.max_depth <= 0 or not direct:
            return []

        began = time.perf_counter()
        visited_ids: set[str] = {c.chunk_id for c in direct}
        visited_symbols: set[str] = {c.symbol for c in direct}
        frontier = self._frontier_from(direct, visited_symbols)
        expanded: list[RetrievedChunk] = []

        for depth in range(1, options.max_depth + 1):
            symbols = [s for s in frontier if s not in visited_symbols][: self._config.max_expansion_frontier]
            if not symbols:
                break
            visited_symbols.update(symbols)

            where = {"symbol": symbols[0]} if len(symbols) == 1 else {"symbol": {"$in": symbols}}
            matches = self._store.fetch(collection, where, limit=self._config.max_expansion_frontier)
            stats.vector_queries += 1

            next_frontier: dict[str, float] = {}
            for match in matches:
                if match.chunk_id in visited_ids:
                    continue
                chunk = self._to_chunk(match, RetrievalSource.DEPENDENCY_EXPANSION, depth=depth)
                chunk.score = round(frontier.get(chunk.symbol, 0.0), 6)
                expanded.append(chunk)
                visited_ids.add(match.chunk_id)
                self._accumulate_frontier(chunk, visited_symbols, next_frontier)
                if len(visited_ids) >= options.max_chunks:
                    break

            frontier = next_frontier
            if len(visited_ids) >= options.max_chunks:
                break

        stats.expansion_ms = round((time.perf_counter() - began) * 1000.0, 2)
        return expanded

    @staticmethod
    def _frontier_from(chunks: list[RetrievedChunk], visited_symbols: set[str]) -> dict[str, float]:
        frontier: dict[str, float] = {}
        for chunk in chunks:
            RepositoryRetriever._accumulate_frontier(chunk, visited_symbols, frontier)
        return frontier

    @staticmethod
    def _accumulate_frontier(
        chunk: RetrievedChunk, visited_symbols: set[str], frontier: dict[str, float]
    ) -> None:
        propagated = chunk.score * 0.82  # dependency relevance decays with distance
        targets = [dep.name for dep in chunk.dependencies if not dep.is_external]
        if chunk.parent_symbol:
            targets.append(chunk.parent_symbol)
        for name in targets:
            if name and name not in visited_symbols:
                frontier[name] = max(frontier.get(name, 0.0), propagated)

    # -- relationships ------------------------------------------------------

    @staticmethod
    def _attach_relationships(results: list[RetrievedChunk]) -> None:
        by_symbol = {c.symbol: c.chunk_id for c in results}
        for chunk in results:
            for dep in chunk.dependencies:
                if dep.is_external:
                    continue
                chunk.relationships.append(RelationshipEdge(
                    relation="depends_on", target_symbol=dep.name,
                    target_chunk_id=by_symbol.get(dep.name),
                ))
            if chunk.parent_symbol:
                chunk.relationships.append(RelationshipEdge(
                    relation="member_of", target_symbol=chunk.parent_symbol,
                    target_chunk_id=by_symbol.get(chunk.parent_symbol),
                ))

    # -- mapping ------------------------------------------------------------

    def _to_chunk(self, match: VectorMatch, source: RetrievalSource, depth: int) -> RetrievedChunk:
        meta = match.metadata
        return RetrievedChunk(
            repository_id=str(meta.get("repository_id", "")),
            chunk_id=match.chunk_id,
            score=round(match.score, 6),
            rank_score=round(match.score, 6),
            chunk_type=str(meta.get("chunk_type", "")),
            symbol=str(meta.get("symbol", "")),
            parent_symbol=str(meta.get("parent_symbol", "")),
            language=str(meta.get("language", "")),
            framework=str(meta.get("framework", "")),
            relative_path=str(meta.get("relative_path", "")),
            start_line=int(meta.get("start_line", 0) or 0),
            end_line=int(meta.get("end_line", 0) or 0),
            visibility=str(meta.get("visibility", "")),
            summary=self._summary(match.document),
            dependencies=self._dependencies(meta),
            content=match.document,
            source=source,
            depth=depth,
        )

    @staticmethod
    def _summary(document: str) -> str | None:
        for line in document.splitlines():
            stripped = line.strip()
            if stripped:
                return stripped[:_SUMMARY_MAX]
        return None

    @staticmethod
    def _dependencies(meta: dict) -> list[ChunkDependencyInfo]:
        raw = meta.get("dependencies") or "[]"
        try:
            data = json.loads(raw) if isinstance(raw, str) else raw
        except (json.JSONDecodeError, TypeError):
            return []
        out: list[ChunkDependencyInfo] = []
        for item in data if isinstance(data, list) else []:
            if isinstance(item, dict) and item.get("name"):
                out.append(ChunkDependencyInfo(
                    name=str(item["name"]), module=str(item.get("module", "")),
                    is_external=bool(item.get("is_external", False)),
                ))
        return out
