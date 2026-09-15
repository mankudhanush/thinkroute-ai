"""Vector store abstraction + ChromaDB implementation.

The indexer depends on the :class:`VectorStore` protocol only, so the storage
backend is replaceable. Two implementations ship here:

  * :class:`ChromaVectorStore` — production store. ChromaDB is imported lazily,
    so the module (and the whole app) still boots when chromadb isn't
    installed; the indexing endpoint then returns a structured 503 instead of
    crashing anything else.
  * :class:`InMemoryVectorStore` — a dependency-free reference implementation
    used for tests and local runs; exercises the exact same interface.

Each repository gets its own collection (``repository_<id>``), never a shared
``all_chunks`` collection. Document ids are the deterministic ``chunk_id`` so
upserts are clean and idempotent.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import Iterable, Protocol

from app.services.repository.embedding_config import EmbeddingSettings
from app.services.repository.embedding_models import ExistingChunk, UpsertRecord
from app.services.repository.exceptions import RepositoryError

logger = logging.getLogger(__name__)

#: Page size when scanning existing collection metadata (bounded memory).
_SCAN_PAGE_SIZE = 1000


@dataclass
class VectorMatch:
    """One search/fetch hit returned by a :class:`VectorStore`.

    ``score`` is a cosine similarity in [0, 1] for vector queries, and 0.0 for
    metadata-only fetches (which are not ranked by similarity).
    """

    chunk_id: str
    score: float
    metadata: dict
    document: str


class VectorStoreError(RepositoryError):
    status_code = 502
    code = "vector_store_error"


class VectorStoreUnavailableError(VectorStoreError):
    status_code = 503
    code = "vector_store_unavailable"


class VectorStore(Protocol):
    """Storage contract the indexer relies on."""

    def existing_index(self, collection: str) -> dict[str, ExistingChunk]:
        """Map of ``chunk_id -> ExistingChunk`` for incremental comparison."""
        ...

    def upsert(self, collection: str, records: list[UpsertRecord]) -> None: ...

    def delete(self, collection: str, ids: list[str]) -> None: ...

    def count(self, collection: str) -> int: ...

    def query(
        self, collection: str, embedding: list[float], top_k: int,
        where: dict | None = None,
    ) -> list[VectorMatch]:
        """Nearest-neighbour search within a single collection."""
        ...

    def fetch(
        self, collection: str, where: dict, limit: int = 500,
    ) -> list[VectorMatch]:
        """Metadata-only lookup (no vector), e.g. resolve chunks by symbol for
        dependency expansion. Not ranked — every match scores 0.0."""
        ...


# ---------------------------------------------------------------------------
# ChromaDB implementation
# ---------------------------------------------------------------------------


class ChromaVectorStore:
    """Persistent ChromaDB store, one collection per repository."""

    def __init__(self, config: EmbeddingSettings) -> None:
        self._config = config
        self._client = None  # lazily constructed on first use

    def _get_client(self):
        if self._client is not None:
            return self._client
        try:
            import chromadb  # imported lazily so absence never breaks app boot
            from chromadb.config import Settings as ChromaConfig
        except ImportError as exc:
            raise VectorStoreUnavailableError(
                "ChromaDB is not installed. Install it with: pip install chromadb"
            ) from exc
        try:
            self._config.chroma_path.mkdir(parents=True, exist_ok=True)
            self._client = chromadb.PersistentClient(
                path=str(self._config.chroma_path),
                settings=ChromaConfig(anonymized_telemetry=False, allow_reset=False),
            )
            logger.info("ChromaDB client ready at %s", self._config.chroma_path)
        except Exception as exc:  # disk/permission/corruption
            raise VectorStoreUnavailableError(f"Could not open ChromaDB store: {exc}") from exc
        return self._client

    def _collection(self, collection: str):
        client = self._get_client()
        try:
            return client.get_or_create_collection(
                name=collection, metadata={"hnsw:space": "cosine"}
            )
        except Exception as exc:
            raise VectorStoreError(f"Could not open collection '{collection}': {exc}") from exc

    def existing_index(self, collection: str) -> dict[str, ExistingChunk]:
        col = self._collection(collection)
        index: dict[str, ExistingChunk] = {}
        offset = 0
        try:
            total = col.count()
            while offset < total:
                page = col.get(include=["metadatas"], limit=_SCAN_PAGE_SIZE, offset=offset)
                ids = page.get("ids") or []
                metadatas = page.get("metadatas") or []
                for chunk_id, meta in zip(ids, metadatas):
                    meta = meta or {}
                    index[chunk_id] = ExistingChunk(
                        content_hash=str(meta.get("content_hash", "")),
                        embedding_version=str(meta.get("embedding_version", "")),
                        created_at=str(meta.get("created_at", "")),
                    )
                if not ids:
                    break
                offset += len(ids)
        except Exception as exc:
            raise VectorStoreError(f"Could not read collection '{collection}': {exc}") from exc
        return index

    def upsert(self, collection: str, records: list[UpsertRecord]) -> None:
        if not records:
            return
        col = self._collection(collection)
        try:
            col.upsert(
                ids=[r.id for r in records],
                embeddings=[r.embedding for r in records],
                metadatas=[r.metadata for r in records],
                documents=[r.document for r in records],
            )
        except Exception as exc:
            raise VectorStoreError(f"Upsert into '{collection}' failed: {exc}") from exc

    def delete(self, collection: str, ids: list[str]) -> None:
        if not ids:
            return
        col = self._collection(collection)
        try:
            col.delete(ids=ids)
        except Exception as exc:
            raise VectorStoreError(f"Delete from '{collection}' failed: {exc}") from exc

    def count(self, collection: str) -> int:
        try:
            return self._collection(collection).count()
        except VectorStoreError:
            raise
        except Exception as exc:
            raise VectorStoreError(f"Count for '{collection}' failed: {exc}") from exc

    def query(
        self, collection: str, embedding: list[float], top_k: int,
        where: dict | None = None,
    ) -> list[VectorMatch]:
        col = self._collection(collection)
        try:
            result = col.query(
                query_embeddings=[embedding],
                n_results=max(1, top_k),
                where=where or None,
                include=["metadatas", "documents", "distances"],
            )
        except Exception as exc:
            raise VectorStoreError(f"Vector search in '{collection}' failed: {exc}") from exc
        return self._matches_from_query(result)

    def fetch(self, collection: str, where: dict, limit: int = 500) -> list[VectorMatch]:
        col = self._collection(collection)
        try:
            result = col.get(where=where or None, limit=limit, include=["metadatas", "documents"])
        except Exception as exc:
            raise VectorStoreError(f"Metadata fetch in '{collection}' failed: {exc}") from exc
        ids = result.get("ids") or []
        metadatas = result.get("metadatas") or []
        documents = result.get("documents") or []
        return [
            VectorMatch(chunk_id=cid, score=0.0, metadata=meta or {}, document=doc or "")
            for cid, meta, doc in zip(ids, metadatas, documents)
        ]

    @staticmethod
    def _matches_from_query(result: dict) -> list[VectorMatch]:
        # Chroma nests query results one list-per-query; we send a single query.
        ids = (result.get("ids") or [[]])[0]
        metadatas = (result.get("metadatas") or [[]])[0]
        documents = (result.get("documents") or [[]])[0]
        distances = (result.get("distances") or [[]])[0]
        matches: list[VectorMatch] = []
        for cid, meta, doc, dist in zip(ids, metadatas, documents, distances):
            # cosine space: distance = 1 - cosine_similarity → similarity = 1 - distance
            score = max(0.0, min(1.0, 1.0 - float(dist)))
            matches.append(VectorMatch(chunk_id=cid, score=score, metadata=meta or {}, document=doc or ""))
        return matches


# ---------------------------------------------------------------------------
# In-memory implementation (reference + tests)
# ---------------------------------------------------------------------------


class InMemoryVectorStore:
    """Dict-backed store implementing the full :class:`VectorStore` interface.

    Not persistent — intended for tests and offline verification of the
    incremental pipeline without ChromaDB.
    """

    def __init__(self) -> None:
        self._collections: dict[str, dict[str, UpsertRecord]] = {}

    def _col(self, collection: str) -> dict[str, UpsertRecord]:
        return self._collections.setdefault(collection, {})

    def existing_index(self, collection: str) -> dict[str, ExistingChunk]:
        out: dict[str, ExistingChunk] = {}
        for chunk_id, record in self._col(collection).items():
            meta = record.metadata
            out[chunk_id] = ExistingChunk(
                content_hash=str(meta.get("content_hash", "")),
                embedding_version=str(meta.get("embedding_version", "")),
                created_at=str(meta.get("created_at", "")),
            )
        return out

    def upsert(self, collection: str, records: list[UpsertRecord]) -> None:
        col = self._col(collection)
        for record in records:
            col[record.id] = record

    def delete(self, collection: str, ids: Iterable[str]) -> None:
        col = self._col(collection)
        for chunk_id in ids:
            col.pop(chunk_id, None)

    def count(self, collection: str) -> int:
        return len(self._col(collection))

    def query(
        self, collection: str, embedding: list[float], top_k: int,
        where: dict | None = None,
    ) -> list[VectorMatch]:
        scored: list[VectorMatch] = []
        for record in self._col(collection).values():
            if where and not self._matches_where(record.metadata, where):
                continue
            score = self._cosine(embedding, record.embedding)
            scored.append(VectorMatch(
                chunk_id=record.id, score=score, metadata=record.metadata, document=record.document,
            ))
        scored.sort(key=lambda m: m.score, reverse=True)
        return scored[: max(1, top_k)]

    def fetch(self, collection: str, where: dict, limit: int = 500) -> list[VectorMatch]:
        out: list[VectorMatch] = []
        for record in self._col(collection).values():
            if self._matches_where(record.metadata, where):
                out.append(VectorMatch(
                    chunk_id=record.id, score=0.0, metadata=record.metadata, document=record.document,
                ))
            if len(out) >= limit:
                break
        return out

    @staticmethod
    def _cosine(a: list[float], b: list[float]) -> float:
        if not a or not b or len(a) != len(b):
            return 0.0
        dot = sum(x * y for x, y in zip(a, b))
        na = math.sqrt(sum(x * x for x in a))
        nb = math.sqrt(sum(y * y for y in b))
        if na == 0 or nb == 0:
            return 0.0
        return max(0.0, min(1.0, dot / (na * nb)))

    @classmethod
    def _matches_where(cls, metadata: dict, where: dict) -> bool:
        """Supports the subset the retriever emits: equality, $eq/$ne/$in, and
        top-level $and/$or composition (mirrors Chroma's where semantics)."""
        for key, condition in where.items():
            if key == "$and":
                if not all(cls._matches_where(metadata, c) for c in condition):
                    return False
            elif key == "$or":
                if not any(cls._matches_where(metadata, c) for c in condition):
                    return False
            elif isinstance(condition, dict):
                value = metadata.get(key)
                for op, operand in condition.items():
                    if op == "$eq" and value != operand:
                        return False
                    if op == "$ne" and value == operand:
                        return False
                    if op == "$in" and value not in operand:
                        return False
            else:
                if metadata.get(key) != condition:
                    return False
        return True
