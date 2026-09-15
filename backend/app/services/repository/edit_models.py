"""Models for Repository AI Editing.

Editing NEVER overwrites files directly: the editor returns a preview (unified
diffs + structured edits + risk), and a separate ``/apply`` call writes changes
only after explicit approval and a conflict check (expected-before hash).
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from app.services.repository.prompt_templates import PromptTaskType
from app.services.repository.retrieval_models import RetrievalFilters


class EditIntent(str, Enum):
    """User-facing edit intent — selects retrieval/prompt emphasis."""

    RENAME_SYMBOL = "rename_symbol"
    REFACTOR_FUNCTION = "refactor_function"
    MODIFY_COMPONENT = "modify_component"
    GENERATE_FILE = "generate_file"
    DELETE_FILE = "delete_file"
    MOVE_FILE = "move_file"
    UPDATE_IMPORTS = "update_imports"
    MODIFY_CONFIG = "modify_config"
    GENERAL_EDIT = "general_edit"


class FileAction(str, Enum):
    """Concrete file operation emitted by the model / applied to disk."""

    CREATE = "create_file"
    MODIFY = "modify_file"
    DELETE = "delete_file"
    MOVE = "move_file"


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class FileEdit(BaseModel):
    """A structured edit (model output, enriched by the editor)."""

    action: FileAction
    path: str
    target_path: str | None = None       # for MOVE
    new_content: str | None = None       # for CREATE / MODIFY / MOVE
    expected_before_hash: str | None = None  # filled by editor for conflict detection


class FileDiff(BaseModel):
    """A previewable, git-compatible diff for one file."""

    path: str
    action: FileAction
    target_path: str | None = None
    before: str = ""
    after: str = ""
    unified_diff: str = ""
    added_lines: int = 0
    removed_lines: int = 0
    risk: RiskLevel = RiskLevel.LOW


class EditRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    repository_id: str = Field(min_length=1)
    repository_path: str = Field(min_length=1)
    instruction: str = Field(min_length=1, max_length=8000)
    intent: EditIntent = EditIntent.GENERAL_EDIT
    provider: str | None = None
    model: str | None = None
    top_k: int | None = Field(default=None, ge=1, le=200)
    filters: RetrievalFilters | None = None
    context_window: str | int = "32k"
    stream: bool = False


class EditResponse(BaseModel):
    repository_id: str
    repository_name: str
    instruction: str
    summary: str
    provider: str
    model: str
    files_changed: list[FileDiff] = Field(default_factory=list)
    patch: str = ""                       # combined unified diff
    edits: list[FileEdit] = Field(default_factory=list)  # pass back to /apply
    overall_risk: RiskLevel = RiskLevel.LOW


class ApplyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    repository_path: str = Field(min_length=1)
    edits: list[FileEdit] = Field(min_length=1)
    approved: bool = False


class AppliedFile(BaseModel):
    path: str
    action: FileAction
    status: str  # "applied" | "conflict" | "missing" | "error"
    detail: str = ""


class ApplyResponse(BaseModel):
    repository_path: str
    applied: list[AppliedFile] = Field(default_factory=list)
    conflicts: list[AppliedFile] = Field(default_factory=list)
    summary: str


class DiffRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    repository_path: str = Field(min_length=1)
    edits: list[FileEdit] = Field(min_length=1)


class DiffResponse(BaseModel):
    files_changed: list[FileDiff] = Field(default_factory=list)
    patch: str = ""
    overall_risk: RiskLevel = RiskLevel.LOW
