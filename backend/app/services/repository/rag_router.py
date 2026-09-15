"""FastAPI router for Repository RAG: context, prompt, and chat.

Exposes ``POST /repository/context``, ``POST /repository/prompt``, and
``POST /repository/chat`` (JSON or SSE stream). Reuses the Phase-4 retriever
singleton and the existing ThinkNRoute routers (``AutoRouter`` / ``ChatService``)
via a thin :class:`MainRouterGateway`. Additive mount only.
"""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse, StreamingResponse

from app.models.schemas import AutoChatRequest, ChatRequest, ProviderId
from app.services.repository.context_builder import ContextBuilder
from app.services.repository.context_models import ContextBuildRequest, RepositoryContext
from app.services.repository.exceptions import RepositoryError
from app.services.repository.prompt_builder import (
    PromptBuilder,
    PromptBuildRequest,
    PromptResult,
)
from app.services.repository.rag_models import RepositoryChatRequest, RepositoryChatResponse
from app.services.repository.rag_service import (
    RepositoryChatService,
    RoutingError,
)
from app.services.repository.retrieval_models import RetrieveRequest
from app.services.repository.retrieval_router import get_retriever

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/repository", tags=["repository-rag"])

_context_builder = ContextBuilder()
_prompt_builder = PromptBuilder()


# ---------------------------------------------------------------------------
# Gateway over the existing routers (reuse — never reimplement routing)
# ---------------------------------------------------------------------------


class MainRouterGateway:
    async def route_auto(self, conversation_id: str, message: str) -> tuple[str, str, str, dict]:
        from app.main import auto_router

        resp = await auto_router.route_and_chat(
            AutoChatRequest(conversation_id=conversation_id, message=message)
        )
        return resp.response, resp.provider.value, resp.model, resp.routing.model_dump()

    async def route_manual(
        self, conversation_id: str, message: str, provider: str | None, model: str | None
    ) -> tuple[str, str, str]:
        from app.main import chat_service, storage_service

        if not provider or not model:
            current = storage_service.current_model()
            if not current:
                raise RoutingError("No provider/model selected. Provide them or select a model first.")
            provider = provider or current["provider"]
            model = model or current["model"]
        try:
            provider_id = ProviderId(provider)
        except ValueError as exc:
            raise RoutingError(f"Unknown provider '{provider}'.") from exc

        resp = await chat_service.chat(ChatRequest(
            conversation_id=conversation_id, provider=provider_id, model=model, message=message
        ))
        return resp.response, resp.provider.value, resp.model


def get_chat_service() -> RepositoryChatService:
    return RepositoryChatService(get_retriever(), _context_builder, _prompt_builder, MainRouterGateway())


def _error_response(exc: RepositoryError) -> JSONResponse:
    logger.warning("Repository RAG failed [%s]: %s", exc.code, exc.detail)
    return JSONResponse(status_code=exc.status_code, content={"error": exc.code, "detail": exc.detail})


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/context", response_model=RepositoryContext)
def build_context(request: ContextBuildRequest) -> RepositoryContext | JSONResponse:
    """Retrieve + organise repository context for a query (no LLM call)."""
    try:
        retrieval = get_retriever().retrieve(RetrieveRequest(
            repository_id=request.repository_id, query=request.query, top_k=request.top_k,
            filters=request.filters, dependency_expansion=request.dependency_expansion,
            max_expansion_depth=request.max_expansion_depth,
        ))
        name = retrieval.results[0].repository_id if retrieval.results else request.repository_id
        return _context_builder.build(
            repository_id=request.repository_id, repository_name=name, query=request.query,
            chunks=retrieval.results, context_window=request.context_window,
            response_reserve_ratio=request.response_reserve_ratio,
        )
    except RepositoryError as exc:
        return _error_response(exc)


@router.post("/prompt", response_model=PromptResult)
def build_prompt(request: PromptBuildRequest) -> PromptResult | JSONResponse:
    """Retrieve + build context + assemble the final prompt (no LLM call)."""
    try:
        retrieval = get_retriever().retrieve(RetrieveRequest(
            repository_id=request.repository_id, query=request.query, top_k=request.top_k,
        ))
        name = retrieval.results[0].repository_id if retrieval.results else request.repository_id
        context = _context_builder.build(
            repository_id=request.repository_id, repository_name=name, query=request.query,
            chunks=retrieval.results, context_window=request.context_window,
        )
        return _prompt_builder.build(context, request.query, request.task)
    except RepositoryError as exc:
        return _error_response(exc)


@router.post("/chat", response_model=RepositoryChatResponse)
async def repository_chat(
    request: RepositoryChatRequest,
    service: RepositoryChatService = Depends(get_chat_service),
):
    """Repository-aware chat (Cursor-style). Set ``stream=true`` for SSE."""
    try:
        if request.stream:
            return StreamingResponse(_sse(service, request), media_type="text/event-stream")
        return await service.chat(request)
    except RepositoryError as exc:
        return _error_response(exc)


async def _sse(service: RepositoryChatService, request: RepositoryChatRequest):
    try:
        async for event in service.chat_stream(request):
            yield f"data: {json.dumps(event)}\n\n"
    except RepositoryError as exc:
        yield f"data: {json.dumps({'event': 'error', 'code': exc.code, 'detail': exc.detail})}\n\n"
