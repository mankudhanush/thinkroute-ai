"""Prompt Assembly Engine.

Converts a :class:`RepositoryContext` + user question + task type into an
optimised prompt: a system message (role, rules, task instructions, output
constraints) and a user message (repository name, summary, the organised
context sections, and the question). Also emits a single combined string so the
prompt can be handed to the existing ThinkNRoute router as one message.
"""

from __future__ import annotations

import logging

from pydantic import BaseModel, ConfigDict, Field

from app.services.repository.chunk_utils import estimate_tokens
from app.services.repository.context_models import ContextChunk, RepositoryContext
from app.services.repository.prompt_templates import (
    REPOSITORY_RULES,
    PromptTaskType,
    get_template,
)

logger = logging.getLogger(__name__)


class PromptMessage(BaseModel):
    role: str
    content: str


class PromptResult(BaseModel):
    task: PromptTaskType
    system_prompt: str
    user_prompt: str
    #: system + user combined — for the router, which accepts one message.
    router_message: str
    messages: list[PromptMessage] = Field(default_factory=list)
    token_estimate: int = 0


class PromptBuildRequest(BaseModel):
    """End-to-end request for ``POST /repository/prompt`` (retrieve+context+prompt)."""

    model_config = ConfigDict(extra="forbid")

    repository_id: str = Field(min_length=1)
    query: str = Field(min_length=1, max_length=8000)
    task: PromptTaskType = PromptTaskType.CODE_EXPLANATION
    top_k: int | None = Field(default=None, ge=1, le=200)
    context_window: str | int = "16k"


class PromptBuilder:
    def build(
        self, context: RepositoryContext, question: str, task: PromptTaskType
    ) -> PromptResult:
        template = get_template(task)
        system_prompt = self._system_prompt(template)
        user_prompt = self._user_prompt(context, question)
        router_message = f"{system_prompt}\n\n{user_prompt}"

        result = PromptResult(
            task=task,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            router_message=router_message,
            messages=[
                PromptMessage(role="system", content=system_prompt),
                PromptMessage(role="user", content=user_prompt),
            ],
            token_estimate=estimate_tokens(router_message),
        )
        logger.info("Prompt built: task=%s ~%d tokens", task.value, result.token_estimate)
        return result

    # -- assembly -----------------------------------------------------------

    @staticmethod
    def _system_prompt(template) -> str:
        return (
            f"{template.role}\n\n"
            f"Task: {template.instructions}\n\n"
            f"{REPOSITORY_RULES}\n\n"
            f"{template.output_constraints}"
        )

    def _user_prompt(self, context: RepositoryContext, question: str) -> str:
        blocks: list[str] = [
            f"# Repository: {context.repository_name}",
            f"Summary: {context.summary}",
        ]
        self._append_section(blocks, "Relevant Components (primary)", context.primary)
        self._append_section(blocks, "Supporting Dependencies", context.supporting_dependencies)
        self._append_section(blocks, "Configuration", context.configuration)
        self._append_section(blocks, "Utilities", context.utilities)
        self._append_section(blocks, "Additional References", context.additional_references)
        blocks.append(f"# User Question\n{question}")
        return "\n\n".join(blocks)

    def _append_section(self, blocks: list[str], title: str, chunks: list[ContextChunk]) -> None:
        if not chunks:
            return
        rendered = "\n\n".join(self._render_chunk(c) for c in chunks)
        blocks.append(f"# {title}\n{rendered}")

    @staticmethod
    def _render_chunk(chunk: ContextChunk) -> str:
        deps = f" | depends on: {', '.join(chunk.dependencies)}" if chunk.dependencies else ""
        note = " (compressed)" if chunk.compressed else ""
        header = (
            f"## {chunk.symbol} ({chunk.chunk_type}) — "
            f"{chunk.relative_path}:{chunk.start_line}-{chunk.end_line}{deps}{note}"
        )
        fence = chunk.language or ""
        return f"{header}\n```{fence}\n{chunk.content}\n```"
