"""Modular prompt templates for the Prompt Assembly Engine.

Each task type maps to a :class:`PromptTemplate` — pure data (role, instructions,
output constraints). The :class:`PromptBuilder` interprets them, so adding or
tuning a template never touches builder logic (Open/Closed). The
``repository_editing`` template pins a strict JSON output contract the Patch
Generator can parse deterministically.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class PromptTaskType(str, Enum):
    GENERAL_QUESTION = "general_question"
    CODE_EXPLANATION = "code_explanation"
    BUG_ANALYSIS = "bug_analysis"
    ARCHITECTURE_REVIEW = "architecture_review"
    REPOSITORY_SEARCH = "repository_search"
    CODE_GENERATION = "code_generation"
    CODE_REFACTORING = "code_refactoring"
    REPOSITORY_EDITING = "repository_editing"


@dataclass(frozen=True)
class PromptTemplate:
    task: PromptTaskType
    role: str
    instructions: str
    output_constraints: str


#: Shared rules injected into every template — grounding + citation discipline.
REPOSITORY_RULES = (
    "Rules:\n"
    "- Use ONLY the repository context provided below; do not invent files, "
    "symbols, or APIs that are not present.\n"
    "- When you reference code, cite the file path and line range shown in the context.\n"
    "- If the provided context is insufficient to answer confidently, say so and "
    "state what additional files would be needed.\n"
    "- Prefer the primary context; use supporting dependencies only for detail."
)

#: The exact JSON contract the editing model must return (parsed by PatchGenerator).
EDIT_OUTPUT_CONTRACT = (
    "Output constraints — return ONLY a single fenced ```json block, no prose, "
    "matching exactly:\n"
    "```json\n"
    "{\n"
    '  "summary": "<one sentence describing the change>",\n'
    '  "edits": [\n'
    '    {"action": "modify_file", "path": "<relative/path>", "new_content": "<FULL new file content>"},\n'
    '    {"action": "create_file", "path": "<relative/path>", "new_content": "<full content>"},\n'
    '    {"action": "delete_file", "path": "<relative/path>"},\n'
    '    {"action": "move_file", "path": "<old/path>", "target_path": "<new/path>", "new_content": "<full content>"}\n'
    "  ]\n"
    "}\n"
    "```\n"
    "For modify_file and move_file you MUST provide the COMPLETE new file "
    "content, not a diff or a fragment. Change only what the request requires."
)

_TEMPLATES: dict[PromptTaskType, PromptTemplate] = {
    PromptTaskType.GENERAL_QUESTION: PromptTemplate(
        PromptTaskType.GENERAL_QUESTION,
        role="You are a senior engineer answering questions about a specific code repository.",
        instructions="Answer the user's question directly and concisely, grounded in the repository context.",
        output_constraints="Be concise. Cite files/lines you rely on.",
    ),
    PromptTaskType.CODE_EXPLANATION: PromptTemplate(
        PromptTaskType.CODE_EXPLANATION,
        role="You are a senior engineer explaining how code in this repository works.",
        instructions=(
            "Explain the relevant code clearly: what it does, how the pieces connect, "
            "and the control/data flow. Walk through the primary component(s) and how "
            "their dependencies participate."
        ),
        output_constraints="Structure the explanation. Reference exact files and line ranges.",
    ),
    PromptTaskType.BUG_ANALYSIS: PromptTemplate(
        PromptTaskType.BUG_ANALYSIS,
        role="You are a senior engineer diagnosing a bug in this repository.",
        instructions=(
            "Identify the likely root cause from the provided code, explain why it "
            "misbehaves, and propose a targeted fix. Note any assumptions."
        ),
        output_constraints="Give: Root cause, Evidence (file:line), Suggested fix.",
    ),
    PromptTaskType.ARCHITECTURE_REVIEW: PromptTemplate(
        PromptTaskType.ARCHITECTURE_REVIEW,
        role="You are a principal architect reviewing this repository's design.",
        instructions=(
            "Assess structure, boundaries, coupling, and notable patterns using the "
            "context. Highlight strengths, risks, and concrete improvements."
        ),
        output_constraints="Give: Overview, Strengths, Risks, Recommendations.",
    ),
    PromptTaskType.REPOSITORY_SEARCH: PromptTemplate(
        PromptTaskType.REPOSITORY_SEARCH,
        role="You are a code search assistant for this repository.",
        instructions=(
            "Locate what the user is asking for. State exactly where it is defined "
            "(file and line range) and give a one-line description of each match."
        ),
        output_constraints="List matches as `path:start-end — description`.",
    ),
    PromptTaskType.CODE_GENERATION: PromptTemplate(
        PromptTaskType.CODE_GENERATION,
        role="You are a senior engineer writing new code consistent with this repository.",
        instructions=(
            "Produce code that matches the repository's conventions, frameworks, and "
            "existing utilities shown in context. Explain where it should live."
        ),
        output_constraints="Provide complete code blocks and the target file path(s).",
    ),
    PromptTaskType.CODE_REFACTORING: PromptTemplate(
        PromptTaskType.CODE_REFACTORING,
        role="You are a senior engineer refactoring code in this repository.",
        instructions=(
            "Improve the code without changing its behavior unless asked. Preserve the "
            "public interface and reuse existing utilities from the context."
        ),
        output_constraints="Show the refactored code and summarize what changed and why.",
    ),
    PromptTaskType.REPOSITORY_EDITING: PromptTemplate(
        PromptTaskType.REPOSITORY_EDITING,
        role=(
            "You are an autonomous coding agent that edits this repository. You output "
            "a machine-readable edit plan; a separate system produces the diff and "
            "applies it only after human approval."
        ),
        instructions=(
            "Translate the user's request into the minimal set of file operations that "
            "accomplish it, consistent with the repository's conventions. Update every "
            "file affected (e.g. rename all references, fix imports). Use exact relative "
            "paths from the context."
        ),
        output_constraints=EDIT_OUTPUT_CONTRACT,
    ),
}


def get_template(task: PromptTaskType) -> PromptTemplate:
    return _TEMPLATES[task]


def available_tasks() -> list[str]:
    return [t.value for t in _TEMPLATES]
