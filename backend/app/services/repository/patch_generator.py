"""Patch generation — parse the model's edit plan into structured edits.

The editing prompt pins a strict JSON contract (see ``prompt_templates``); this
module extracts and validates that JSON into :class:`FileEdit` objects. It is
deliberately forgiving about surrounding prose (models sometimes wrap JSON in a
fenced block) but strict about structure, raising a structured error otherwise.
No files are read or written here.
"""

from __future__ import annotations

import json
import logging
import re

from app.services.repository.edit_models import FileAction, FileEdit
from app.services.repository.exceptions import RepositoryError

logger = logging.getLogger(__name__)

_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)


class PatchParseError(RepositoryError):
    status_code = 422
    code = "patch_parse_error"


class PatchGenerator:
    def parse(self, llm_output: str) -> tuple[str, list[FileEdit]]:
        """Return (summary, edits) parsed from the model output."""
        payload = self._extract_json(llm_output)
        summary = str(payload.get("summary", "")).strip() or "Repository edit"
        raw_edits = payload.get("edits")
        if not isinstance(raw_edits, list) or not raw_edits:
            raise PatchParseError("Edit plan contained no 'edits' array.")
        edits = [self._to_edit(item, i) for i, item in enumerate(raw_edits)]
        logger.info("Parsed edit plan: %d operation(s)", len(edits))
        return summary, edits

    # -- internals ----------------------------------------------------------

    def _extract_json(self, text: str) -> dict:
        candidate = None
        fence = _JSON_FENCE_RE.search(text)
        if fence:
            candidate = fence.group(1)
        else:
            start, end = text.find("{"), text.rfind("}")
            if start != -1 and end > start:
                candidate = text[start : end + 1]
        if candidate is None:
            raise PatchParseError("No JSON edit plan found in the model output.")
        try:
            data = json.loads(candidate)
        except json.JSONDecodeError as exc:
            raise PatchParseError(f"Edit plan is not valid JSON: {exc.msg}") from exc
        if not isinstance(data, dict):
            raise PatchParseError("Edit plan must be a JSON object.")
        return data

    def _to_edit(self, item: object, index: int) -> FileEdit:
        if not isinstance(item, dict):
            raise PatchParseError(f"Edit #{index} is not an object.")
        action_raw = str(item.get("action", "")).strip()
        try:
            action = FileAction(action_raw)
        except ValueError as exc:
            raise PatchParseError(
                f"Edit #{index} has invalid action '{action_raw}'. "
                f"Expected one of: {[a.value for a in FileAction]}."
            ) from exc

        path = str(item.get("path", "")).strip()
        if not path:
            raise PatchParseError(f"Edit #{index} is missing 'path'.")

        target_path = item.get("target_path")
        new_content = item.get("new_content")

        if action in (FileAction.CREATE, FileAction.MODIFY) and new_content is None:
            raise PatchParseError(f"Edit #{index} ({action.value}) requires 'new_content'.")
        if action is FileAction.MOVE and not target_path:
            raise PatchParseError(f"Edit #{index} (move_file) requires 'target_path'.")

        return FileEdit(
            action=action,
            path=path,
            target_path=str(target_path) if target_path else None,
            new_content=str(new_content) if new_content is not None else None,
        )
