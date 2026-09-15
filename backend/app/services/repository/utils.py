"""Small, reusable, side-effect-free helpers shared across the module.

Each function does exactly one thing so the scanner/parser/aggregator can be
composed from tested primitives rather than duplicated inline logic.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

from app.services.repository.constants import (
    CONFIG_FILE_NAMES,
    LANGUAGE_BY_EXTENSION,
)
from app.services.repository.exceptions import UnsupportedEncodingError
from app.services.repository.models import FileCategory, Language

#: Encodings attempted, in order, when reading a text file.
_TEXT_ENCODINGS: tuple[str, ...] = ("utf-8", "utf-8-sig", "utf-16", "latin-1")

_STYLE_LANGUAGES = {Language.CSS, Language.SCSS}
_MARKUP_LANGUAGES = {Language.HTML, Language.XML, Language.VUE, Language.SVELTE}
_DATA_LANGUAGES = {Language.JSON, Language.YAML, Language.TOML}
_SOURCE_LANGUAGES = {
    Language.PYTHON, Language.JAVASCRIPT, Language.JSX, Language.TYPESCRIPT,
    Language.TSX, Language.JAVA, Language.KOTLIN, Language.GO, Language.RUST,
    Language.CSHARP, Language.DART, Language.SHELL, Language.SQL,
}


def human_readable_size(num_bytes: int) -> str:
    """Format a byte count as a compact human string (e.g. ``1.4 MB``)."""
    size = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024.0 or unit == "TB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{size:.1f} PB"


def extension_of(name: str) -> str:
    """Lower-cased suffix including the dot, or ``""`` if none."""
    return Path(name).suffix.lower()


def is_hidden(name: str) -> bool:
    """True for dot-files/dot-dirs (``.env``, ``.git``) but not ``.`` / ``..``."""
    return name.startswith(".") and name not in (".", "..")


def detect_language(name: str) -> Language:
    """Map a file name to a :class:`Language` via its extension."""
    return LANGUAGE_BY_EXTENSION.get(extension_of(name), Language.UNKNOWN)


def is_config_file(name: str) -> bool:
    return name.lower() in CONFIG_FILE_NAMES


def categorize(language: Language, name: str) -> FileCategory:
    """Classify a file for statistics/UX grouping."""
    if is_config_file(name):
        return FileCategory.CONFIG
    if language in _SOURCE_LANGUAGES:
        return FileCategory.SOURCE
    if language in _STYLE_LANGUAGES:
        return FileCategory.STYLE
    if language in _MARKUP_LANGUAGES:
        return FileCategory.MARKUP
    if language is Language.MARKDOWN:
        return FileCategory.DOCUMENTATION
    if language in _DATA_LANGUAGES:
        return FileCategory.DATA
    return FileCategory.OTHER


def looks_binary(sample: bytes) -> bool:
    """Heuristic binary sniff: a NUL byte in the head is a reliable signal."""
    return b"\x00" in sample


def read_text(path: str, sample_for_binary: int = 0) -> str:
    """Read a text file, trying several encodings.

    :param sample_for_binary: if > 0, read that many head bytes first and raise
        :class:`UnsupportedEncodingError` when the sample looks binary — avoids
        loading a large opaque blob fully into memory.
    :raises UnsupportedEncodingError: when no encoding decodes the file.
    """
    if sample_for_binary > 0:
        with open(path, "rb") as handle:
            head = handle.read(sample_for_binary)
        if looks_binary(head):
            raise UnsupportedEncodingError(path, "File appears to be binary.")

    for encoding in _TEXT_ENCODINGS:
        try:
            with open(path, "r", encoding=encoding) as handle:
                return handle.read()
        except (UnicodeDecodeError, UnicodeError):
            continue
    raise UnsupportedEncodingError(path, "No supported text encoding decoded the file.")


def count_lines(text: str) -> int:
    if not text:
        return 0
    # Count newlines, +1 when the final line has no trailing newline.
    return text.count("\n") + (0 if text.endswith("\n") else 1)


def content_hash(text: str) -> str:
    """Stable SHA-256 of file content — the key for future incremental
    re-indexing (unchanged hash ⇒ skip re-parse/re-embed)."""
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()


def to_relative(absolute_path: str, root: str) -> str:
    """Return a POSIX-style path relative to ``root`` (stable across OSes)."""
    rel = os.path.relpath(absolute_path, root)
    return Path(rel).as_posix()


def top_segment(specifier: str) -> str:
    """First path/package segment of an import specifier.

    ``"app.services.foo"`` -> ``"app"``; ``"@scope/pkg/sub"`` -> ``"@scope/pkg"``;
    ``"react-dom/client"`` -> ``"react-dom"``.
    """
    spec = specifier.strip()
    if spec.startswith("@") and "/" in spec:
        scope, _, rest = spec.partition("/")
        return f"{scope}/{rest.split('/')[0]}"
    if "/" in spec:
        return spec.split("/")[0]
    if "." in spec:
        return spec.split(".")[0]
    return spec
