"""ThinkNRoute Repository RAG service.

Wires the Repository Intelligence pipeline into the EXISTING routing engine:

    query → Retriever → Context Builder → Prompt Builder → (Auto|Manual) Router
          → Gemini / Groq / Ollama → answer

Routing is NOT reimplemented: Auto mode delegates to the existing
``AutoRouter`` and Manual mode to the existing ``ChatService`` (both of which
already handle provider selection, failover, conversation history, and
persistence). Repository mode simply injects repository context into the
message before routing.
"""

from __future__ import annotations

import logging
import time
from typing import AsyncIterator, Protocol

from app.services.repository.context_builder import ContextBuilder
from app.services.repository.context_models import RepositoryContext
from app.services.repository.exceptions import RepositoryError
from app.services.repository.prompt_builder import PromptBuilder, PromptResult
from app.services.repository.rag_models import (
    ChatMode,
    ContextSummary,
    RepositoryChatRequest,
    RepositoryChatResponse,
    RetrievalSummary,
    SourceReference,
)
from app.services.repository.retrieval_models import RetrieveRequest, RetrieveResponse
from app.services.repository.retriever import RepositoryRetriever

logger = logging.getLogger(__name__)


class RoutingError(RepositoryError):
    status_code = 400
    code = "routing_error"


class RouterGateway(Protocol):
    """Adapter over the existing routers so the RAG service depends on an
    interface, not on ``app.main`` — keeps it testable and decoupled."""

    async def route_auto(self, conversation_id: str, message: str) -> tuple[str, str, str, dict]:
        """Return (answer, provider, model, routing_metadata)."""
        ...

    async def route_manual(
        self, conversation_id: str, message: str, provider: str | None, model: str | None
    ) -> tuple[str, str, str]:
        """Return (answer, provider, model)."""
        ...


class RepositoryChatService:
    def __init__(
        self,
        retriever: RepositoryRetriever,
        context_builder: ContextBuilder,
        prompt_builder: PromptBuilder,
        router_gateway: RouterGateway,
    ) -> None:
        self._retriever = retriever
        self._context_builder = context_builder
        self._prompt_builder = prompt_builder
        self._router = router_gateway

    # -- non-streaming ------------------------------------------------------

    async def chat(self, request: RepositoryChatRequest) -> RepositoryChatResponse:
        retrieval, context, prompt = self._prepare(request)

        if request.mode is ChatMode.AUTO:
            answer, provider, model, routing = await self._router.route_auto(
                request.conversation_id, prompt.router_message
            )
        else:
            answer, provider, model = await self._router.route_manual(
                request.conversation_id, prompt.router_message, request.provider, request.model
            )
            routing = None

        return self._response(request, retrieval, context, prompt, answer, provider, model, routing)

    # -- streaming (SSE event dicts) ----------------------------------------

    async def chat_stream(self, request: RepositoryChatRequest) -> AsyncIterator[dict]:
        yield {"event": "progress", "stage": "retrieving", "message": "Searching the repository index…"}
        retrieval, context, prompt = self._prepare(request)
        yield {
            "event": "progress", "stage": "context_built",
            "message": f"Built context from {context.statistics.included_chunks} chunks "
                       f"({context.statistics.used_tokens} tokens).",
        }
        yield {"event": "sources", "sources": [s.model_dump() for s in self._sources(context)]}
        yield {"event": "progress", "stage": "routing", "message": "Routing to a provider…"}

        if request.mode is ChatMode.AUTO:
            answer, provider, model, routing = await self._router.route_auto(
                request.conversation_id, prompt.router_message
            )
        else:
            answer, provider, model = await self._router.route_manual(
                request.conversation_id, prompt.router_message, request.provider, request.model
            )
            routing = None

        yield {"event": "answer_meta", "provider": provider, "model": model, "routing": routing}
        for piece in self._chunk_text(answer):
            yield {"event": "answer", "delta": piece}
        yield {"event": "done"}

    # -- shared pipeline ----------------------------------------------------

    def _prepare(
        self, request: RepositoryChatRequest
    ) -> tuple[RetrieveResponse, RepositoryContext, PromptResult]:
        retrieval = self._retriever.retrieve(RetrieveRequest(
            repository_id=request.repository_id,
            query=request.query,
            top_k=request.top_k,
            filters=request.filters,
            dependency_expansion=request.dependency_expansion,
            max_expansion_depth=request.max_expansion_depth,
        ))
        context = self._context_builder.build(
            repository_id=request.repository_id,
            repository_name=retrieval.results[0].repository_id if retrieval.results else request.repository_id,
            query=request.query,
            chunks=retrieval.results,
            context_window=request.context_window,
        )
        prompt = self._prompt_builder.build(context, request.query, request.task)
        return retrieval, context, prompt

    def _response(
        self, request, retrieval, context, prompt, answer, provider, model, routing
    ) -> RepositoryChatResponse:
        return RepositoryChatResponse(
            conversation_id=request.conversation_id,
            repository_id=request.repository_id,
            query=request.query,
            answer=answer,
            mode=request.mode,
            provider=provider,
            model=model,
            task=request.task,
            retrieval=RetrievalSummary(
                chunks_retrieved=retrieval.statistics.chunks_retrieved,
                chunks_expanded=retrieval.statistics.chunks_expanded,
                final_result_count=retrieval.statistics.final_result_count,
            ),
            context=ContextSummary(
                window_tokens=context.statistics.window_tokens,
                used_tokens=context.statistics.used_tokens,
                included_chunks=context.statistics.included_chunks,
                trimmed_chunks=context.statistics.trimmed_chunks,
            ),
            sources=self._sources(context),
            routing=routing,
        )

    @staticmethod
    def _sources(context: RepositoryContext) -> list[SourceReference]:
        cited = [*context.primary, *context.supporting_dependencies]
        return [
            SourceReference(
                symbol=c.symbol, chunk_type=c.chunk_type, relative_path=c.relative_path,
                start_line=c.start_line, end_line=c.end_line, score=c.score,
            )
            for c in cited
        ]

    @staticmethod
    def _chunk_text(text: str, size: int = 48) -> list[str]:
        """Split a finished answer into deltas so clients can render it as a
        stream (provider adapters return a full string, not a token stream)."""
        return [text[i : i + size] for i in range(0, len(text), size)] or [""]
