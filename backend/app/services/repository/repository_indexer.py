"""Repository Indexing Engine — the incremental indexing orchestrator.

Pipeline (fully streaming — one file's chunks in memory at a time):

    repository → ChunkGenerator.iter_chunks → hash comparison →
    batch embed (changed/new only) → upsert → delete removed → statistics

Named ``RepositoryIndexingEngine`` to avoid colliding with the Phase-1
``RepositoryIndexer`` (metadata extraction). Reuses — never modifies — the
scanner, detectors, and chunk generator. All collaborators are injected, so
the embedding provider and vector store are swappable and the whole engine is
unit-testable without Ollama or ChromaDB.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Iterator

from app.services.repository.chunk_models import Chunk
from app.services.repository.chunk_utils import repository_id_for
from app.services.repository.chunker import ChunkGenerator, ChunkerConfig
from app.services.repository.constants import DEFAULT_SCAN_SETTINGS, ScanSettings
from app.services.repository.detector import FrameworkDetector, LanguageDetector
from app.services.repository.embedding_config import EmbeddingSettings, embedding_settings
from app.services.repository.embedding_models import (
    ChunkAction,
    ExistingChunk,
    IndexBuildRequest,
    IndexBuildResponse,
    IndexStatistics,
    StoredChunkMetadata,
    UpsertRecord,
    utc_now_iso,
)
from app.services.repository.embedding_service import EmbeddingService
from app.services.repository.exceptions import RepositoryError
from app.services.repository.scanner import RepositoryScanner
from app.services.repository.vector_store import VectorStore

logger = logging.getLogger(__name__)


class IndexingError(RepositoryError):
    status_code = 422
    code = "indexing_failed"


class _PendingBatch:
    """Accumulates changed/new chunks until the batch size is reached, then
    embeds + upserts them in one shot. Keeps the engine's main loop readable
    and guarantees embeddings are never generated one-by-one."""

    def __init__(
        self,
        engine: "RepositoryIndexingEngine",
        collection: str,
        embedding_version: str,
        batch_size: int,
        stats: IndexStatistics,
    ) -> None:
        self._engine = engine
        self._collection = collection
        self._embedding_version = embedding_version
        self._batch_size = batch_size
        self._stats = stats
        self._chunks: list[Chunk] = []
        self._actions: list[ChunkAction] = []
        self._created_at: list[str] = []

    def add(self, chunk: Chunk, action: ChunkAction, created_at: str) -> None:
        self._chunks.append(chunk)
        self._actions.append(action)
        self._created_at.append(created_at)
        if len(self._chunks) >= self._batch_size:
            self.flush()

    def flush(self) -> None:
        if not self._chunks:
            return
        now = utc_now_iso()
        texts = [self._engine.embedding_text(c) for c in self._chunks]
        vectors = self._engine.embeddings.embed(texts)

        records: list[UpsertRecord] = []
        for chunk, vector, action, created in zip(self._chunks, vectors, self._actions, self._created_at):
            metadata = StoredChunkMetadata.from_chunk(
                chunk, embedding_version=self._embedding_version,
                created_at=created, updated_at=now,
            )
            records.append(UpsertRecord(
                id=chunk.chunk_id, embedding=vector,
                metadata=metadata.to_chroma(), document=chunk.content,
            ))
            if action is ChunkAction.INSERTED:
                self._stats.embedded_chunks += 1
            else:
                self._stats.updated_chunks += 1

        self._engine.store.upsert(self._collection, records)
        logger.info("Upserted %d chunks into '%s'", len(records), self._collection)
        self._chunks.clear()
        self._actions.clear()
        self._created_at.clear()


class RepositoryIndexingEngine:
    def __init__(
        self,
        chunk_generator: ChunkGenerator,
        embedding_service: EmbeddingService,
        vector_store: VectorStore,
        config: EmbeddingSettings = embedding_settings,
        scan_settings: ScanSettings = DEFAULT_SCAN_SETTINGS,
        framework_detector: FrameworkDetector | None = None,
        language_detector: LanguageDetector | None = None,
    ) -> None:
        self._chunks = chunk_generator
        self.embeddings = embedding_service
        self.store = vector_store
        self._config = config
        self._scan_settings = scan_settings
        self._frameworks = framework_detector or FrameworkDetector()
        self._languages = language_detector or LanguageDetector()

    # -- helpers ------------------------------------------------------------

    @staticmethod
    def embedding_text(chunk: Chunk) -> str:
        """Text handed to the embedder: a small locating header + the code, so
        the vector captures *where/what* as well as the body."""
        header = f"{chunk.relative_path} :: {chunk.symbol_name} ({chunk.chunk_type})"
        return f"{header}\n{chunk.content}" if chunk.content else header

    # -- public API ---------------------------------------------------------

    def build_index(self, request: IndexBuildRequest) -> IndexBuildResponse:
        started = time.perf_counter()
        config = self._config.with_overrides(batch_size=request.batch_size, model=request.model)
        run_settings = self._scan_settings.with_overrides(
            max_file_size_bytes=request.max_file_size_bytes
        )
        scanner = RepositoryScanner(run_settings)

        root = scanner.validate_root(request.repository_path)
        scanned, _tally = scanner.scan(root)
        if not scanned:
            raise IndexingError("No supported, readable files were found to index.")

        repository_name = os.path.basename(root.rstrip(os.sep)) or root
        repository_id = repository_id_for(root)
        collection = config.collection_name(repository_id)
        detections = self._frameworks.detect(root)
        primary_framework = detections[0].name if detections else None
        primary_language, _secondary = self._languages.primary_and_secondary(scanned)

        logger.info(
            "Index build started: repo=%s id=%s collection=%s files=%d model=%s version=%s",
            repository_name, repository_id, collection, len(scanned),
            self.embeddings.model, config.embedding_version,
        )

        existing = {} if request.recreate else self._load_existing(collection)
        if request.recreate and existing:
            logger.info("recreate=True — ignoring %d existing vectors (full re-embed)", len(existing))

        stats = IndexStatistics()
        seen_ids: set[str] = set()
        batch = _PendingBatch(self, collection, config.embedding_version, config.batch_size, stats)

        for chunk in self._iter_repo_chunks(
            root, scanned, repository_id, repository_name, primary_framework, config
        ):
            stats.total_chunks += 1
            seen_ids.add(chunk.chunk_id)
            self._route_chunk(chunk, existing, config.embedding_version, batch, stats)

        batch.flush()
        self._delete_removed(collection, existing, seen_ids, stats)

        stats.embedding_batches = self.embeddings.batches_run
        stats.embedding_ms = round(self.embeddings.total_embedding_ms, 2)
        stats.collection_size = self.store.count(collection)
        stats.indexing_ms = round((time.perf_counter() - started) * 1000.0, 2)

        logger.info(
            "Index build complete: %s | embedded=%d updated=%d skipped=%d deleted=%d "
            "| batches=%d embed=%.0fms total=%.0fms | collection_size=%d",
            repository_name, stats.embedded_chunks, stats.updated_chunks, stats.skipped_chunks,
            stats.deleted_chunks, stats.embedding_batches, stats.embedding_ms,
            stats.indexing_ms, stats.collection_size,
        )

        return IndexBuildResponse(
            repository_id=repository_id, repository_name=repository_name, root_path=root,
            primary_language=str(primary_language) if primary_language else None,
            primary_framework=primary_framework, collection_name=collection,
            embedding_model=self.embeddings.model, embedding_version=config.embedding_version,
            chunks_embedded=stats.embedded_chunks, chunks_updated=stats.updated_chunks,
            chunks_skipped=stats.skipped_chunks, chunks_deleted=stats.deleted_chunks,
            statistics=stats,
        )

    # -- internals ----------------------------------------------------------

    def _iter_repo_chunks(
        self, root: str, scanned, repository_id: str, repository_name: str,
        framework: str | None, config: EmbeddingSettings,
    ) -> Iterator[Chunk]:
        # Embedding requires content, so force it on regardless of defaults.
        chunker_config = ChunkerConfig(include_content=True)
        return self._chunks.iter_chunks(
            root, scanned, repository_id=repository_id, repository_name=repository_name,
            framework=framework, config=chunker_config,
        )

    def _load_existing(self, collection: str) -> dict[str, ExistingChunk]:
        existing = self.store.existing_index(collection)
        logger.info("Loaded %d existing vectors from '%s' for incremental diff", len(existing), collection)
        return existing

    @staticmethod
    def _route_chunk(
        chunk: Chunk, existing: dict[str, ExistingChunk], embedding_version: str,
        batch: _PendingBatch, stats: IndexStatistics,
    ) -> None:
        prior = existing.get(chunk.chunk_id)
        if prior is not None and prior.content_hash == chunk.hash and prior.embedding_version == embedding_version:
            stats.skipped_chunks += 1  # unchanged — reuse the stored vector
            return
        if prior is None:
            batch.add(chunk, ChunkAction.INSERTED, created_at=utc_now_iso())
        else:  # changed content or stale embedding version → re-embed, keep created_at
            batch.add(chunk, ChunkAction.UPDATED, created_at=prior.created_at or utc_now_iso())

    def _delete_removed(
        self, collection: str, existing: dict[str, ExistingChunk], seen_ids: set[str],
        stats: IndexStatistics,
    ) -> None:
        removed = [cid for cid in existing if cid not in seen_ids]
        if removed:
            self.store.delete(collection, removed)
            stats.deleted_chunks = len(removed)
            logger.info("Deleted %d removed chunks from '%s'", len(removed), collection)
