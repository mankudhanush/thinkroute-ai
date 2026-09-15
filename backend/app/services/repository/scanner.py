"""Repository scanner: recursive, streaming traversal.

Responsibilities (and *only* these):
  * walk the tree, pruning ignored / hidden / vendored directories,
  * skip binary, oversized, and lock/noise files,
  * yield a lightweight :class:`ScannedFile` per accepted file,
  * collect per-directory metadata and ignore/skip counts.

It never opens a file for parsing — that is the parser's job. Traversal is a
generator so a 100k-file repository streams through with bounded memory, which
is the seam future incremental indexing plugs into.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Iterator

from app.services.repository.constants import BINARY_SNIFF_BYTES, ScanSettings
from app.services.repository.exceptions import (
    InvalidRepositoryPathError,
    RepositoryPermissionError,
)
from app.services.repository.models import DirectoryMetadata, Language, ScannedFile
from app.services.repository.utils import (
    detect_language,
    extension_of,
    is_hidden,
    looks_binary,
    to_relative,
)

logger = logging.getLogger(__name__)


@dataclass
class ScanTally:
    """Running counters produced alongside the streamed files."""

    accepted: int = 0
    ignored_files: int = 0          # lock/noise/binary/hidden files skipped
    oversized: int = 0              # exceeded the size limit
    permission_errors: int = 0
    directories: dict[str, DirectoryMetadata] = field(default_factory=dict)


class RepositoryScanner:
    """Streams accepted files from a repository root.

    Single responsibility, no parsing, no I/O beyond ``os.walk``/``stat`` and a
    tiny binary sniff. Injected :class:`ScanSettings` make policy testable.
    """

    def __init__(self, settings: ScanSettings) -> None:
        self._settings = settings

    # -- public API ---------------------------------------------------------

    def validate_root(self, root: str) -> str:
        """Resolve and validate the repository root, returning its abspath."""
        abspath = os.path.abspath(os.path.expanduser(root))
        if not os.path.exists(abspath):
            raise InvalidRepositoryPathError(f"Path does not exist: {root}")
        if not os.path.isdir(abspath):
            raise InvalidRepositoryPathError(f"Path is not a directory: {root}")
        if not os.access(abspath, os.R_OK):
            raise RepositoryPermissionError(f"Path is not readable: {root}")
        return abspath

    def scan(self, root: str) -> tuple[list[ScannedFile], ScanTally]:
        """Eagerly collect the scan into a list + tally.

        Thin wrapper over :meth:`iter_scan` for callers that want the whole
        result; large-repo callers can iterate the generator directly.
        """
        tally = ScanTally()
        files = list(self.iter_scan(root, tally))
        logger.info(
            "Repository scan complete: %d accepted, %d ignored, %d oversized, "
            "%d permission errors across %d directories",
            tally.accepted, tally.ignored_files, tally.oversized,
            tally.permission_errors, len(tally.directories),
        )
        return files, tally

    def iter_scan(self, root: str, tally: ScanTally) -> Iterator[ScannedFile]:
        """Yield accepted files one at a time, updating ``tally`` in place."""
        abspath = self.validate_root(root)
        logger.info("Repository scan started: %s", abspath)

        for current_dir, dirnames, filenames in os.walk(
            abspath, topdown=True, onerror=self._on_walk_error,
            followlinks=self._settings.follow_symlinks,
        ):
            # Prune ignored subdirectories in place (topdown lets us skip them).
            dirnames[:] = [d for d in sorted(dirnames) if not self._skip_dir(d)]

            dir_meta = self._directory_meta(abspath, current_dir, dirnames)
            tally.directories[dir_meta.relative_path] = dir_meta

            for filename in sorted(filenames):
                scanned = self._process_file(abspath, current_dir, filename, tally)
                if scanned is None:
                    continue
                dir_meta.file_count += 1
                dir_meta.languages[scanned.language.value] = (
                    dir_meta.languages.get(scanned.language.value, 0) + 1
                )
                tally.accepted += 1
                yield scanned

    # -- internals ----------------------------------------------------------

    def _skip_dir(self, name: str) -> bool:
        if name in self._settings.ignored_directories:
            return True
        if self._settings.ignore_hidden and is_hidden(name):
            return True
        return False

    def _directory_meta(
        self, root: str, current_dir: str, dirnames: list[str]
    ) -> DirectoryMetadata:
        rel = to_relative(current_dir, root)
        return DirectoryMetadata(
            relative_path="." if rel == "." else rel,
            name=os.path.basename(current_dir) or os.path.basename(root),
            subdirectory_count=len(dirnames),
        )

    def _process_file(
        self, root: str, current_dir: str, filename: str, tally: ScanTally
    ) -> ScannedFile | None:
        """Decide whether a file is accepted; return it or ``None`` (skipped)."""
        lower = filename.lower()

        if lower in self._settings.ignored_file_names:
            tally.ignored_files += 1
            return None
        if self._settings.ignore_hidden and is_hidden(filename):
            tally.ignored_files += 1
            return None

        ext = extension_of(filename)
        if ext in self._settings.binary_extensions:
            tally.ignored_files += 1
            return None

        absolute = os.path.join(current_dir, filename)
        try:
            size = os.path.getsize(absolute)
        except PermissionError:
            tally.permission_errors += 1
            logger.warning("Permission denied (stat): %s", absolute)
            return None
        except OSError as exc:  # broken symlink, race, etc.
            logger.warning("Could not stat %s: %s", absolute, exc)
            tally.ignored_files += 1
            return None

        if size > self._settings.max_file_size_bytes:
            tally.oversized += 1
            logger.debug("Skipping oversized file (%d bytes): %s", size, absolute)
            return None

        if self._sniff_binary(absolute):
            tally.ignored_files += 1
            return None

        return ScannedFile(
            absolute_path=absolute,
            relative_path=to_relative(absolute, root),
            name=filename,
            extension=ext,
            size_bytes=size,
            language=detect_language(filename),
        )

    def _sniff_binary(self, absolute: str) -> bool:
        """Cheap content check for extension-less or mislabelled binaries."""
        try:
            with open(absolute, "rb") as handle:
                return looks_binary(handle.read(BINARY_SNIFF_BYTES))
        except PermissionError:
            logger.warning("Permission denied (read): %s", absolute)
            return True
        except OSError:
            return True

    def _on_walk_error(self, error: OSError) -> None:
        """os.walk error callback — log and continue, never abort the scan."""
        logger.warning("Traversal error at %s: %s", getattr(error, "filename", "?"), error)


def unknown_language_ratio(files: list[ScannedFile]) -> float:
    """Fraction of scanned files whose language is unknown (diagnostics only)."""
    if not files:
        return 0.0
    unknown = sum(1 for f in files if f.language is Language.UNKNOWN)
    return unknown / len(files)
