"""Unified-diff generation for Repository AI Editing.

Produces git-compatible unified diffs (``--- a/… / +++ b/…``) from a before/after
pair for each :class:`FileEdit`, computes added/removed line counts, and assigns
a risk level. Pure/stdlib (``difflib``) — no repository writes happen here.
"""

from __future__ import annotations

import difflib
import os

from app.services.repository.edit_models import FileAction, FileDiff, FileEdit, RiskLevel

_HIGH_RISK_ACTIONS = {FileAction.DELETE, FileAction.MOVE}
_CONFIG_HINTS = ("config", "package.json", ".env", "tsconfig", "requirements", "pyproject", "dockerfile")


class DiffGenerator:
    def build(self, repo_root: str, edit: FileEdit, before: str) -> FileDiff:
        after = "" if edit.action is FileAction.DELETE else (edit.new_content or "")
        display_path = edit.target_path if edit.action is FileAction.MOVE else edit.path
        unified = self._unified(edit.path, display_path, before, after, edit.action)
        added, removed = self._counts(before, after)
        return FileDiff(
            path=edit.path,
            action=edit.action,
            target_path=edit.target_path,
            before=before,
            after=after,
            unified_diff=unified,
            added_lines=added,
            removed_lines=removed,
            risk=self._risk(edit, added, removed),
        )

    # -- helpers ------------------------------------------------------------

    @staticmethod
    def _unified(old_path: str, new_path: str, before: str, after: str, action: FileAction) -> str:
        from_label = "/dev/null" if action is FileAction.CREATE else f"a/{old_path}"
        to_label = "/dev/null" if action is FileAction.DELETE else f"b/{new_path}"
        diff = difflib.unified_diff(
            before.splitlines(keepends=True),
            after.splitlines(keepends=True),
            fromfile=from_label,
            tofile=to_label,
            lineterm="\n",
        )
        text = "".join(diff)
        if text and not text.endswith("\n"):
            text += "\n"
        return text or f"# no textual change for {old_path}\n"

    @staticmethod
    def _counts(before: str, after: str) -> tuple[int, int]:
        added = removed = 0
        for line in difflib.ndiff(before.splitlines(), after.splitlines()):
            if line.startswith("+ "):
                added += 1
            elif line.startswith("- "):
                removed += 1
        return added, removed

    def _risk(self, edit: FileEdit, added: int, removed: int) -> RiskLevel:
        if edit.action in _HIGH_RISK_ACTIONS:
            return RiskLevel.HIGH
        lowered = edit.path.lower()
        if any(hint in lowered for hint in _CONFIG_HINTS):
            return RiskLevel.MEDIUM
        churn = added + removed
        if churn == 0:
            return RiskLevel.LOW
        if churn > 120:
            return RiskLevel.HIGH
        if churn > 30:
            return RiskLevel.MEDIUM
        return RiskLevel.LOW

    @staticmethod
    def combine(diffs: list[FileDiff]) -> str:
        return "\n".join(d.unified_diff for d in diffs if d.unified_diff)

    @staticmethod
    def overall_risk(diffs: list[FileDiff]) -> RiskLevel:
        order = {RiskLevel.LOW: 0, RiskLevel.MEDIUM: 1, RiskLevel.HIGH: 2}
        worst = max((order[d.risk] for d in diffs), default=0)
        return [RiskLevel.LOW, RiskLevel.MEDIUM, RiskLevel.HIGH][worst]
