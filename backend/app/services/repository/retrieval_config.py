"""Configuration for the Repository Retriever.

Env-driven with safe defaults (mirrors the project's config pattern). Every
retrieval knob — top-k, similarity threshold, dependency expansion, expansion
depth, result caps, reranker choice — is here; nothing is hard-coded at a call
site. Per-request overrides are applied on top of these defaults.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, replace


@dataclass(frozen=True)
class RetrievalSettings:
    top_k: int
    similarity_threshold: float
    enable_dependency_expansion: bool
    max_expansion_depth: int
    max_expansion_frontier: int
    max_retrieved_chunks: int
    #: Multiplier applied to top_k when fetching from the store, to give the
    #: reranker headroom (and absorb post-query path filtering).
    fetch_multiplier: int
    reranker: str

    def with_overrides(self, **changes: object) -> "RetrievalSettings":
        clean = {k: v for k, v in changes.items() if v is not None}
        return replace(self, **clean) if clean else self


def _load() -> RetrievalSettings:
    return RetrievalSettings(
        top_k=int(os.getenv("RETRIEVAL_TOP_K", "10")),
        similarity_threshold=float(os.getenv("RETRIEVAL_SIMILARITY_THRESHOLD", "0.0")),
        enable_dependency_expansion=os.getenv("RETRIEVAL_DEPENDENCY_EXPANSION", "true").lower() == "true",
        max_expansion_depth=int(os.getenv("RETRIEVAL_MAX_EXPANSION_DEPTH", "1")),
        max_expansion_frontier=int(os.getenv("RETRIEVAL_MAX_EXPANSION_FRONTIER", "50")),
        max_retrieved_chunks=int(os.getenv("RETRIEVAL_MAX_RETRIEVED_CHUNKS", "50")),
        fetch_multiplier=int(os.getenv("RETRIEVAL_FETCH_MULTIPLIER", "3")),
        reranker=os.getenv("RETRIEVAL_RERANKER", "vector"),
    )


retrieval_settings = _load()
