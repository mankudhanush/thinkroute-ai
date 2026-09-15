"""Exception hierarchy for the Repository Intelligence Engine.

Every failure mode the module can hit has a dedicated type carrying an HTTP
status hint, so the router can translate them uniformly without leaking
implementation details. The engine itself never raises bare ``Exception``.
"""

from __future__ import annotations


class RepositoryError(Exception):
    """Base class for all repository-engine failures.

    ``status_code`` and ``code`` let the FastAPI layer build a consistent
    error envelope without importing internals.
    """

    status_code: int = 400
    code: str = "repository_error"

    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


class InvalidRepositoryPathError(RepositoryError):
    """The supplied path does not exist or is not a directory."""

    status_code = 404
    code = "invalid_repository_path"


class RepositoryPermissionError(RepositoryError):
    """The process lacks permission to read the path or one of its entries."""

    status_code = 403
    code = "repository_permission_denied"


class EmptyRepositoryError(RepositoryError):
    """The path is valid but contained no supported/readable files."""

    status_code = 422
    code = "empty_repository"


# --- Non-fatal, per-file conditions -----------------------------------------
# These are surfaced as warnings/metadata during a scan and never abort the
# whole index operation; they exist so callers (and the parser) can react to a
# specific cause rather than a generic error.


class FileProcessingError(RepositoryError):
    """Base for recoverable, single-file problems raised during scan/parse."""

    status_code = 422
    code = "file_processing_error"

    def __init__(self, path: str, detail: str) -> None:
        super().__init__(detail)
        self.path = path


class FileTooLargeError(FileProcessingError):
    """File exceeds the configured maximum size and was skipped."""

    code = "file_too_large"


class UnsupportedEncodingError(FileProcessingError):
    """File could not be decoded with any supported text encoding."""

    code = "unsupported_encoding"


class CorruptedFileError(FileProcessingError):
    """File appears to be binary/corrupted despite a text-like extension."""

    code = "corrupted_file"


class ParserError(FileProcessingError):
    """A language parser failed on otherwise readable content."""

    code = "parser_error"
