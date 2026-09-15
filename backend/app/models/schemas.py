from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ProviderId(str, Enum):
    GEMINI = "gemini"
    GROQ = "groq"
    CLOUDFLARE = "cloudflare"
    OLLAMA = "ollama"


class ConnectRequest(BaseModel):
    provider: ProviderId
    api_key: str | None = Field(default=None, min_length=1)
    optional_base_url: str | None = None

    @field_validator("optional_base_url")
    @classmethod
    def normalize_base_url(cls, value: str | None) -> str | None:
        return value.rstrip("/") if value else value


class ModelInfo(BaseModel):
    id: str
    name: str
    provider: ProviderId
    context_window: int | None = None
    owned_by: str | None = None


class ProviderStatus(BaseModel):
    provider: ProviderId
    name: str
    connected: bool
    available_models: list[ModelInfo] = Field(default_factory=list)
    connected_at: datetime | None = None


class ConnectResponse(BaseModel):
    provider: ProviderId
    status: str
    connected: bool
    available_models: list[ModelInfo] = Field(default_factory=list)


class ModelSelectionRequest(BaseModel):
    provider: ProviderId
    model: str = Field(min_length=1)


class CurrentModelResponse(BaseModel):
    provider: ProviderId
    model: str


class ChatRequest(BaseModel):
    conversation_id: str = Field(min_length=1, max_length=200)
    provider: ProviderId
    model: str = Field(min_length=1)
    message: str = Field(min_length=1, max_length=100_000)

    @field_validator("conversation_id", "message")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("Value cannot be empty")
        return stripped


class ContextMessageInfo(BaseModel):
    role: str
    content: str
    score: float = 0.0


class ContextInfo(BaseModel):
    """What the Context-Aware Memory Engine selected for this turn — surfaced
    to the UI so routing/memory is explainable."""
    used: bool = False
    thread_id: str = ""
    is_new_topic: bool = False
    used_count: int = 0
    total_history: int = 0
    reason: str = ""
    messages: list[ContextMessageInfo] = Field(default_factory=list)
    topic_keywords: list[str] = Field(default_factory=list)
    engine_ms: float = 0.0


class ChatResponse(BaseModel):
    conversation_id: str
    provider: ProviderId
    model: str
    response: str
    created_at: datetime
    context: ContextInfo | None = None


class HistoryMessage(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    role: str
    content: str
    provider: ProviderId
    model: str
    created_at: datetime


class HealthResponse(BaseModel):
    status: str
    service: str


class AutoChatRequest(BaseModel):
    conversation_id: str = Field(min_length=1, max_length=200)
    message: str = Field(min_length=1, max_length=100_000)

    @field_validator("conversation_id", "message")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("Value cannot be empty")
        return stripped


class RoutingMetadata(BaseModel):
    intent: str
    complexity: str
    confidence: float
    estimated_output: str = "medium"
    requires_reasoning: bool = False
    requires_code: bool = False
    requires_long_context: bool = False
    offline_possible: bool = True
    reason: str = ""
    classified_by: str = "rule"  # "rule" | "model" | "fallback"

    # Per-stage timing (milliseconds) for observability.
    classification_ms: float = 0.0
    routing_ms: float = 0.0
    provider_ms: float = 0.0
    total_ms: float = 0.0


class AutoChatResponse(BaseModel):
    conversation_id: str
    provider: ProviderId
    model: str
    response: str
    created_at: datetime
    routing: RoutingMetadata
    context: ContextInfo | None = None


