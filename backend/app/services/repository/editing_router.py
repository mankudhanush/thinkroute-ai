"""FastAPI router for Repository AI Editing.

Exposes ``POST /repository/edit`` (preview: diff + patch, JSON or SSE stream),
``POST /repository/apply`` (write, requires approval + passes conflict checks),
and ``POST /repository/diff`` (standalone unified diff, no LLM). Reuses the
Phase-4 retriever and the existing provider/routing singletons via
:class:`LlmGateway`. Additive mount only — no existing route touched.
"""

from __future__ import annotations

import json
import logging
from functools import lru_cache

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse, StreamingResponse

from app.services.repository.context_builder import ContextBuilder
from app.services.repository.diff_generator import DiffGenerator
from app.services.repository.edit_models import (
    ApplyRequest,
    ApplyResponse,
    DiffRequest,
    DiffResponse,
    EditRequest,
    EditResponse,
)
from app.services.repository.exceptions import RepositoryError
from app.services.repository.llm_gateway import LlmGateway
from app.services.repository.patch_generator import PatchGenerator
from app.services.repository.prompt_builder import PromptBuilder
from app.services.repository.repository_editor import RepositoryEditor
from app.services.repository.retrieval_router import get_retriever

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/repository", tags=["repository-editing"])


def _build_llm_gateway() -> LlmGateway:
    """Wire the gateway from the existing app singletons (reuse, not rebuild)."""
    from app.main import (
        provider_service,
        storage_service,
        hybrid_classifier,
        routing_engine,
        model_selector_service,
    )

    return LlmGateway(
        provider_service, storage_service, hybrid_classifier,
        routing_engine, model_selector_service,
    )


@lru_cache(maxsize=1)
def _default_editor() -> RepositoryEditor:
    return RepositoryEditor(
        retriever=get_retriever(),
        context_builder=ContextBuilder(),
        prompt_builder=PromptBuilder(),
        llm_gateway=_build_llm_gateway(),
        patch_generator=PatchGenerator(),
        diff_generator=DiffGenerator(),
    )


def get_editor() -> RepositoryEditor:
    return _default_editor()


def _error(exc: RepositoryError) -> JSONResponse:
    logger.warning("Repository editing failed [%s]: %s", exc.code, exc.detail)
    return JSONResponse(status_code=exc.status_code, content={"error": exc.code, "detail": exc.detail})


@router.post("/edit", response_model=EditResponse)
async def edit(request: EditRequest, editor: RepositoryEditor = Depends(get_editor)):
    """Generate an edit preview (unified diff + patch). Never writes files.
    Set ``stream=true`` for SSE progress + result."""
    try:
        if request.stream:
            return StreamingResponse(_sse_edit(editor, request), media_type="text/event-stream")
        return await editor.generate_edit(request)
    except RepositoryError as exc:
        return _error(exc)


@router.post("/apply", response_model=ApplyResponse)
def apply(request: ApplyRequest, editor: RepositoryEditor = Depends(get_editor)) -> ApplyResponse | JSONResponse:
    """Apply previously-previewed edits to disk. Requires ``approved=true`` and
    passes per-file conflict checks."""
    try:
        return editor.apply(request)
    except RepositoryError as exc:
        return _error(exc)


@router.post("/diff", response_model=DiffResponse)
def diff(request: DiffRequest, editor: RepositoryEditor = Depends(get_editor)) -> DiffResponse | JSONResponse:
    """Produce unified diffs for a set of proposed file edits (no LLM)."""
    try:
        return editor.build_diffs(request)
    except RepositoryError as exc:
        return _error(exc)


async def _sse_edit(editor: RepositoryEditor, request: EditRequest):
    try:
        async for event in editor.generate_edit_stream(request):
            yield f"data: {json.dumps(event)}\n\n"
    except RepositoryError as exc:
        yield f"data: {json.dumps({'event': 'error', 'code': exc.code, 'detail': exc.detail})}\n\n"
