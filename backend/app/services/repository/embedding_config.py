"""Configuration for the Repository Indexing Engine.

All tunables (provider, model, batch size, collection prefix, embedding
version, ChromaDB location, timeouts) are read from environment variables with
safe defaults — nothing is hard-coded at a call site. Mirrors the existing
``app.config`` pattern (frozen dataclass + a module-level singleton), and
reuses the project's Ollama base URL / data directory as defaults.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, replace
from pathlib import Path

from app.config import settings


def _default_chroma_path() -> Path:
    raw = os.getenv("CHROMA_PATH")
    if raw:
        path = Path(raw)
    else:
        # Sit next to the existing SQLite DB by default (./data/chroma).
        path = settings.database_path.parent / "chroma"
    return path if path.is_absolute() else (Path.cwd() / path)


@dataclass(frozen=True)
class EmbeddingSettings:
    """Immutable indexing configuration. Use :meth:`with_overrides` to derive a
    per-request variant (e.g. a caller-supplied batch size / model)."""

    provider: str
    model: str
    batch_size: int
    collection_prefix: str
    embedding_version: str
    chroma_path: Path
    ollama_base_url: str
    request_timeout_seconds: float
    max_retries: int
    embedding_dimensions: int | None

    def collection_name(self, repository_id: str) -> str:
        """Per-repository collection name — never a shared 'all_chunks'."""
        return f"{self.collection_prefix}{repository_id}"

    def with_overrides(self, **changes: object) -> "EmbeddingSettings":
        clean = {k: v for k, v in changes.items() if v is not None}
        return replace(self, **clean) if clean else self


def _load() -> EmbeddingSettings:
    model = os.getenv("EMBEDDING_MODEL", "nomic-embed-text")
    return EmbeddingSettings(
        provider=os.getenv("EMBEDDING_PROVIDER", "ollama"),
        model=model,
        batch_size=int(os.getenv("EMBEDDING_BATCH_SIZE", "8")),
        collection_prefix=os.getenv("EMBEDDING_COLLECTION_PREFIX", "repository_"),
        # Bump this (or change the model) to force a full re-embed on next build.
        embedding_version=os.getenv("EMBEDDING_VERSION", f"{model}@v1"),
        chroma_path=_default_chroma_path(),
        ollama_base_url=os.getenv("EMBEDDING_OLLAMA_BASE_URL", settings.ollama_base_url),
        request_timeout_seconds=float(os.getenv("EMBEDDING_TIMEOUT_SECONDS", "60")),
        max_retries=int(os.getenv("EMBEDDING_MAX_RETRIES", "2")),
        embedding_dimensions=(
            int(os.environ["EMBEDDING_DIMENSIONS"])
            if os.getenv("EMBEDDING_DIMENSIONS")
            else None
        ),
    )


embedding_settings = _load()
