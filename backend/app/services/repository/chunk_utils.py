"""Reusable, side-effect-free helpers for the Intelligent Chunk Generator.

Grouped by concern:
  * **Identity/hashing** — deterministic chunk ids + content hashes.
  * **Slicing** — turn (start, end) line spans into text.
  * **Span detection** — brace matching, because the heuristic JS/C-family
    parsers report only a declaration line; the chunker recovers the block
    extent here (semantically, via matched braces — never a fixed line count).
  * **Logical splitting** — divide an oversized symbol at blank-line / block
    boundaries.
  * **Semantics** — visibility inference and chunk-level dependency resolution.
"""

from __future__ import annotations

import hashlib
import re

from app.services.repository.models import ImportMetadata, Language, ScannedFile
from app.services.repository.utils import top_segment

_IDENTIFIER_RE = re.compile(r"[A-Za-z_$][A-Za-z0-9_$]*")


# ---------------------------------------------------------------------------
# Identity & hashing
# ---------------------------------------------------------------------------


def stable_chunk_id(
    repository: str, relative_path: str, symbol_name: str, chunk_type: str, start_line: int
) -> str:
    """Deterministic chunk id — identical inputs always yield the same id, so
    re-indexing an unchanged repository produces identical ids (enabling
    incremental embedding/upsert later). Never random."""
    seed = f"{repository}\x1f{relative_path}\x1f{symbol_name}\x1f{chunk_type}\x1f{start_line}"
    return hashlib.sha1(seed.encode("utf-8")).hexdigest()  # noqa: S324 (id, not security)


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()


def repository_id_for(root_abspath: str) -> str:
    """Stable repository id derived from its location."""
    return hashlib.sha1(root_abspath.encode("utf-8")).hexdigest()[:16]  # noqa: S324


def estimate_tokens(text: str) -> int:
    """Cheap token estimate (~4 chars/token) for future embedding budgeting."""
    return max(1, len(text) // 4) if text else 0


# ---------------------------------------------------------------------------
# Slicing
# ---------------------------------------------------------------------------


def slice_lines(lines: list[str], start_line: int, end_line: int) -> str:
    """Join 1-indexed inclusive ``[start_line, end_line]`` back into text."""
    start = max(1, start_line)
    end = min(len(lines), end_line)
    if end < start:
        return ""
    return "\n".join(lines[start - 1 : end])


def line_count_of(text: str) -> int:
    if not text:
        return 0
    return text.count("\n") + (0 if text.endswith("\n") else 1)


# ---------------------------------------------------------------------------
# Span detection (brace matching for parsers that only give a declaration line)
# ---------------------------------------------------------------------------


def find_block_end(lines: list[str], start_line: int, max_lookahead: int = 4000) -> int:
    """Return the 1-indexed end line of a brace-delimited block that opens at
    or shortly after ``start_line``.

    Skips braces inside strings and comments so it is stable across ordinary
    code. If no ``{`` is found near the declaration (e.g. a one-line
    ``type X = ...;`` or an arrow returning an expression), the end of the
    statement (terminating ``;`` or the declaration line) is returned.
    """
    n = len(lines)
    idx = start_line - 1
    depth = 0
    paren = 0  # (...) nesting — braces inside params/generics are not the body
    opened = False
    in_block_comment = False
    limit = min(n, start_line + max_lookahead)

    for line_no in range(idx, limit):
        line = lines[line_no]
        i = 0
        while i < len(line):
            two = line[i : i + 2]
            if in_block_comment:
                if two == "*/":
                    in_block_comment = False
                    i += 2
                    continue
                i += 1
                continue
            if two == "//":
                break  # rest of line is a comment
            if two == "/*":
                in_block_comment = True
                i += 2
                continue
            ch = line[i]
            if ch in "\"'`":
                i = _skip_string(line, i, ch)
                continue
            if ch == "(":
                paren += 1
            elif ch == ")":
                paren = max(0, paren - 1)
            elif ch == "{" and paren == 0:
                depth += 1
                opened = True
            elif ch == "}" and paren == 0:
                depth -= 1
                if opened and depth == 0:
                    return line_no + 1
            elif ch == ";" and not opened and paren == 0:
                return line_no + 1  # statement without a block body
            i += 1

    # No balanced close found — fall back to the declaration line itself.
    return start_line if not opened else min(limit, n)


def _skip_string(line: str, i: int, quote: str) -> int:
    """Advance past a quoted string starting at ``line[i] == quote``."""
    i += 1
    while i < len(line):
        if line[i] == "\\":
            i += 2
            continue
        if line[i] == quote:
            return i + 1
        i += 1
    return i  # unterminated on this line (e.g. template literal) — stop here


# ---------------------------------------------------------------------------
# Logical splitting of oversized symbols
# ---------------------------------------------------------------------------


def split_into_blocks(
    lines: list[str], start_line: int, end_line: int, min_block_lines: int = 8
) -> list[tuple[int, int]]:
    """Divide ``[start_line, end_line]`` into logical blocks at blank-line
    boundaries. Adjacent small groups are merged so no block is trivially
    short. Returns 1-indexed inclusive ranges. Never cuts mid-statement.
    """
    groups: list[tuple[int, int]] = []
    current_start: int | None = None
    for ln in range(start_line, end_line + 1):
        blank = not lines[ln - 1].strip()
        if blank:
            if current_start is not None:
                groups.append((current_start, ln - 1))
                current_start = None
        elif current_start is None:
            current_start = ln
    if current_start is not None:
        groups.append((current_start, end_line))

    if not groups:
        return [(start_line, end_line)]

    # Merge groups forward until each reaches the minimum block size.
    merged: list[tuple[int, int]] = []
    for s, e in groups:
        if merged and (merged[-1][1] - merged[-1][0] + 1) < min_block_lines:
            merged[-1] = (merged[-1][0], e)
        else:
            merged.append((s, e))
    return merged


# ---------------------------------------------------------------------------
# Visibility
# ---------------------------------------------------------------------------

_JS_LANGS = {Language.JAVASCRIPT, Language.JSX, Language.TYPESCRIPT, Language.TSX}


def infer_visibility(
    name: str, language: Language, *, is_exported: bool, declaration_line: str = ""
) -> "Visibility":
    from app.services.repository.chunk_models import Visibility

    decl = declaration_line.strip()
    if language is Language.PYTHON:
        if name.startswith("__") and name.endswith("__"):
            return Visibility.PUBLIC  # dunder (e.g. __init__) is a public protocol
        if name.startswith("__"):
            return Visibility.PRIVATE
        if name.startswith("_"):
            return Visibility.PROTECTED
        return Visibility.PUBLIC
    if language in _JS_LANGS:
        if name.startswith("#") or name.startswith("_"):
            return Visibility.PRIVATE
        return Visibility.PUBLIC if is_exported else Visibility.INTERNAL
    if language in (Language.JAVA, Language.CSHARP):
        if "private" in decl:
            return Visibility.PRIVATE
        if "protected" in decl:
            return Visibility.PROTECTED
        if "public" in decl:
            return Visibility.PUBLIC
        return Visibility.INTERNAL
    if language is Language.GO:
        return Visibility.PUBLIC if name[:1].isupper() else Visibility.INTERNAL
    if language is Language.RUST:
        return Visibility.PUBLIC if decl.lstrip().startswith("pub") else Visibility.PRIVATE
    return Visibility.PUBLIC if is_exported else Visibility.INTERNAL


# ---------------------------------------------------------------------------
# Dependency resolution (chunk-level)
# ---------------------------------------------------------------------------


def identifiers_in(text: str) -> set[str]:
    """Set of identifier tokens appearing in ``text``."""
    return set(_IDENTIFIER_RE.findall(text))


def _bound_names(imp: ImportMetadata) -> list[str]:
    """Names an import introduces into scope (for reference matching)."""
    names = list(imp.names)
    if imp.alias:
        names.append(imp.alias)
    if not names:  # side-effect / namespace import — key on the module tail
        names.append(top_segment(imp.module).split("/")[-1])
    return names


def resolve_chunk_dependencies(content: str, imports: list[ImportMetadata]):
    """Return the imported symbols this chunk actually references.

    e.g. a ``Navbar`` component whose body mentions ``Button``, ``ThemeProvider``
    and ``cn`` yields exactly those three dependencies. Powers dependency-aware
    retrieval in a later phase.
    """
    from app.services.repository.chunk_models import ChunkDependency

    tokens = identifiers_in(content)
    seen: set[tuple[str, str]] = set()
    deps: list[ChunkDependency] = []
    for imp in imports:
        for name in _bound_names(imp):
            if name and name in tokens and (name, imp.module) not in seen:
                seen.add((name, imp.module))
                deps.append(
                    ChunkDependency(
                        name=name,
                        module=imp.module,
                        is_external=imp.is_external,
                        is_relative=imp.is_relative,
                    )
                )
    return deps


# ---------------------------------------------------------------------------
# Internal/external classification (mirrors the Phase-1 resolver, decoupled)
# ---------------------------------------------------------------------------


def top_level_names(scanned: list[ScannedFile]) -> set[str]:
    names: set[str] = set()
    for f in scanned:
        head, _, tail = f.relative_path.partition("/")
        names.add(head if tail else f.name.rsplit(".", 1)[0])
    return names


def refine_import_locality(imports: list[ImportMetadata], internal_names: set[str]) -> None:
    """Update ``is_external`` in place: relative or repo-local ⇒ internal."""
    for imp in imports:
        internal = imp.is_relative or top_segment(imp.module) in internal_names
        imp.is_external = not internal
