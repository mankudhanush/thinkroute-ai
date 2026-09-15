"""Repository AI Editor.

Orchestrates repository-aware editing:

    instruction → Retriever → Context Builder → Prompt Builder → LLM →
    Patch Generator → Diff Generator → preview (never writes)

Applying changes is a SEPARATE, explicit step (:meth:`apply`) that requires
``approved=true`` and verifies each file's expected-before hash to detect
conflicts. All writes are confined to the repository root (path-traversal
guard). Collaborators are injected; the LLM call reuses provider integrations
via :class:`LlmGateway`.
"""

from __future__ import annotations

import logging
import os
from typing import AsyncIterator

from app.providers.base_provider import ChatTurn
from app.services.repository.chunk_utils import content_hash
from app.services.repository.context_builder import ContextBuilder
from app.services.repository.diff_generator import DiffGenerator
from app.services.repository.edit_models import (
    AppliedFile,
    ApplyRequest,
    ApplyResponse,
    DiffRequest,
    DiffResponse,
    EditRequest,
    EditResponse,
    FileAction,
    FileDiff,
    FileEdit,
)
from app.services.repository.exceptions import (
    InvalidRepositoryPathError,
    RepositoryError,
)
from app.services.repository.llm_gateway import LlmGateway
from app.services.repository.patch_generator import PatchGenerator
from app.services.repository.prompt_builder import PromptBuilder
from app.services.repository.prompt_templates import PromptTaskType
from app.services.repository.retrieval_models import RetrieveRequest
from app.services.repository.retriever import RepositoryRetriever
from app.services.repository.utils import read_text

logger = logging.getLogger(__name__)


class EditValidationError(RepositoryError):
    status_code = 422
    code = "edit_validation_error"


class MissingFileError(RepositoryError):
    status_code = 404
    code = "edit_missing_file"


class EditConflictError(RepositoryError):
    status_code = 409
    code = "edit_conflict"


class PathOutsideRepositoryError(RepositoryError):
    status_code = 400
    code = "path_outside_repository"


class ApprovalRequiredError(RepositoryError):
    status_code = 403
    code = "approval_required"


class RepositoryEditor:
    def __init__(
        self,
        retriever: RepositoryRetriever,
        context_builder: ContextBuilder,
        prompt_builder: PromptBuilder,
        llm_gateway: LlmGateway,
        patch_generator: PatchGenerator,
        diff_generator: DiffGenerator,
    ) -> None:
        self._retriever = retriever
        self._context = context_builder
        self._prompt = prompt_builder
        self._llm = llm_gateway
        self._patch = patch_generator
        self._diff = diff_generator

    # -- generate preview (async: calls the model) --------------------------

    async def generate_edit(self, request: EditRequest) -> EditResponse:
        root = self._validate_root(request.repository_path)
        summary, edits, provider, model = await self._plan(request, root)
        diffs = self._prepare(root, edits)
        return EditResponse(
            repository_id=request.repository_id,
            repository_name=os.path.basename(root.rstrip(os.sep)) or root,
            instruction=request.instruction,
            summary=summary,
            provider=provider,
            model=model,
            files_changed=diffs,
            patch=self._diff.combine(diffs),
            edits=edits,
            overall_risk=self._diff.overall_risk(diffs),
        )

    async def generate_edit_stream(self, request: EditRequest) -> AsyncIterator[dict]:
        yield {"event": "progress", "stage": "retrieving", "message": "Finding relevant code…"}
        root = self._validate_root(request.repository_path)
        yield {"event": "progress", "stage": "prompting", "message": "Building edit prompt…"}
        summary, edits, provider, model = await self._plan(request, root)
        yield {"event": "progress", "stage": "diffing", "message": f"Generating diffs via {provider}/{model}…"}
        diffs = self._prepare(root, edits)
        response = EditResponse(
            repository_id=request.repository_id,
            repository_name=os.path.basename(root.rstrip(os.sep)) or root,
            instruction=request.instruction, summary=summary, provider=provider, model=model,
            files_changed=diffs, patch=self._diff.combine(diffs), edits=edits,
            overall_risk=self._diff.overall_risk(diffs),
        )
        yield {"event": "result", "result": response.model_dump()}
        yield {"event": "done"}

    async def _plan(self, request: EditRequest, root: str):
        retrieval = self._retriever.retrieve(RetrieveRequest(
            repository_id=request.repository_id, query=request.instruction,
            top_k=request.top_k, filters=request.filters,
        ))
        name = os.path.basename(root.rstrip(os.sep)) or root
        context = self._context.build(
            repository_id=request.repository_id, repository_name=name,
            query=request.instruction, chunks=retrieval.results,
            context_window=request.context_window,
        )
        prompt = self._prompt.build(context, request.instruction, PromptTaskType.REPOSITORY_EDITING)
        messages = [ChatTurn(m.role, m.content) for m in prompt.messages]
        text, provider, model = await self._llm.complete(
            messages, routing_hint=request.instruction, provider=request.provider, model=request.model,
        )
        summary, edits = self._patch.parse(text)
        return summary, edits, provider, model

    # -- standalone diff (no LLM) -------------------------------------------

    def build_diffs(self, request: DiffRequest) -> DiffResponse:
        root = self._validate_root(request.repository_path)
        diffs = self._prepare(root, list(request.edits))
        return DiffResponse(
            files_changed=diffs, patch=self._diff.combine(diffs),
            overall_risk=self._diff.overall_risk(diffs),
        )

    # -- apply (sync: writes to disk, after approval) -----------------------

    def apply(self, request: ApplyRequest) -> ApplyResponse:
        if not request.approved:
            raise ApprovalRequiredError("Changes must be explicitly approved before applying.")
        root = self._validate_root(request.repository_path)
        applied: list[AppliedFile] = []
        conflicts: list[AppliedFile] = []

        for edit in request.edits:
            outcome = self._apply_one(root, edit)
            (applied if outcome.status == "applied" else conflicts).append(outcome)

        summary = f"Applied {len(applied)} change(s); {len(conflicts)} skipped."
        logger.info("Apply: %s", summary)
        return ApplyResponse(
            repository_path=root, applied=applied, conflicts=conflicts, summary=summary
        )

    # -- internals ----------------------------------------------------------

    @staticmethod
    def _validate_root(path: str) -> str:
        root = os.path.abspath(os.path.expanduser(path))
        if not os.path.isdir(root):
            raise InvalidRepositoryPathError(f"Repository path is not a directory: {path}")
        return root

    def _safe_join(self, root: str, relative: str) -> str:
        absolute = os.path.abspath(os.path.join(root, relative))
        if os.path.commonpath([root, absolute]) != root:
            raise PathOutsideRepositoryError(f"Refusing to touch a path outside the repository: {relative}")
        return absolute

    def _read_if_exists(self, absolute: str) -> str | None:
        if not os.path.isfile(absolute):
            return None
        try:
            return read_text(absolute)
        except RepositoryError:
            return None

    def _prepare(self, root: str, edits: list[FileEdit]) -> list[FileDiff]:
        """Validate each edit against the working tree, stamp expected-before
        hashes for conflict detection, and produce diffs. Raises on missing/
        conflicting files (the safety checks)."""
        diffs: list[FileDiff] = []
        for edit in edits:
            absolute = self._safe_join(root, edit.path)
            before = self._read_if_exists(absolute)

            if edit.action in (FileAction.MODIFY, FileAction.DELETE, FileAction.MOVE) and before is None:
                raise MissingFileError(f"Cannot {edit.action.value}: file not found — {edit.path}")
            if edit.action is FileAction.CREATE and before is not None:
                raise EditConflictError(f"Cannot create: file already exists — {edit.path}")
            if edit.action is FileAction.MOVE and edit.target_path:
                target_abs = self._safe_join(root, edit.target_path)
                if os.path.exists(target_abs):
                    raise EditConflictError(f"Cannot move: target already exists — {edit.target_path}")

            edit.expected_before_hash = content_hash(before) if before is not None else None
            diffs.append(self._diff.build(root, edit, before or ""))
        return diffs

    def _apply_one(self, root: str, edit: FileEdit) -> AppliedFile:
        try:
            absolute = self._safe_join(root, edit.path)
        except PathOutsideRepositoryError as exc:
            return AppliedFile(path=edit.path, action=edit.action, status="error", detail=exc.detail)

        current = self._read_if_exists(absolute)
        current_hash = content_hash(current) if current is not None else None

        # Conflict: the working tree changed since the diff was generated.
        if edit.expected_before_hash is not None and edit.expected_before_hash != current_hash:
            return AppliedFile(path=edit.path, action=edit.action, status="conflict",
                               detail="File changed since the diff was generated.")

        try:
            return self._write(root, absolute, edit, current)
        except OSError as exc:
            return AppliedFile(path=edit.path, action=edit.action, status="error", detail=str(exc))

    def _write(self, root: str, absolute: str, edit: FileEdit, current: str | None) -> AppliedFile:
        if edit.action is FileAction.DELETE:
            if current is None:
                return AppliedFile(path=edit.path, action=edit.action, status="missing", detail="Already absent.")
            os.remove(absolute)
            return AppliedFile(path=edit.path, action=edit.action, status="applied", detail="Deleted.")

        if edit.action is FileAction.MOVE:
            if current is None:
                return AppliedFile(path=edit.path, action=edit.action, status="missing", detail="Source absent.")
            target_abs = self._safe_join(root, edit.target_path or edit.path)
            self._write_file(target_abs, edit.new_content if edit.new_content is not None else current)
            os.remove(absolute)
            return AppliedFile(path=edit.path, action=edit.action, status="applied",
                               detail=f"Moved to {edit.target_path}.")

        # CREATE / MODIFY
        self._write_file(absolute, edit.new_content or "")
        verb = "Created" if edit.action is FileAction.CREATE else "Modified"
        return AppliedFile(path=edit.path, action=edit.action, status="applied", detail=f"{verb}.")

    @staticmethod
    def _write_file(absolute: str, content: str) -> None:
        os.makedirs(os.path.dirname(absolute) or ".", exist_ok=True)
        with open(absolute, "w", encoding="utf-8", newline="") as handle:
            handle.write(content)
