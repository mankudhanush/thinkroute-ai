"""Models for ThinkNRoute Repository RAG (chat) integration."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from app.services.repository.prompt_templates import PromptTaskType
from app.services.repository.retrieval_models import RetrievalFilters


class ChatMode(str, Enum):
    AUTO = "auto"        # reuse the existing intent-based Auto router
    MANUAL = "manual"    # caller pins provider + model


class SourceReference(BaseModel):
    """A citation surfaced to the UI — where an answer's context came from."""

    symbol: str
    chunk_type: str
    relative_path: str
    start_line: int
    end_line: int
    score: float


class RetrievalSummary(BaseModel):
    chunks_retrieved: int
    chunks_expanded: int
    final_result_count: int


class ContextSummary(BaseModel):
    window_tokens: int
    used_tokens: int
    included_chunks: int
    trimmed_chunks: int


class RepositoryChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    conversation_id: str = Field(min_length=1, max_length=200)
    repository_id: str = Field(min_length=1)
    query: str = Field(min_length=1, max_length=8000)
    mode: ChatMode = ChatMode.AUTO
    provider: str | None = None       # manual mode
    model: str | None = None          # manual mode
    task: PromptTaskType = PromptTaskType.CODE_EXPLANATION
    top_k: int | None = Field(default=None, ge=1, le=200)
    filters: RetrievalFilters | None = None
    dependency_expansion: bool | None = None
    max_expansion_depth: int | None = Field(default=None, ge=0, le=5)
    context_window: str | int = "16k"
    stream: bool = False


class RepositoryChatResponse(BaseModel):
    conversation_id: str
    repository_id: str
    query: str
    answer: str
    mode: ChatMode
    provider: str
    model: str
    task: PromptTaskType
    retrieval: RetrievalSummary
    context: ContextSummary
    sources: list[SourceReference] = Field(default_factory=list)
    routing: dict | None = None  # populated in Auto mode (intent/provider reasoning)
