"""Framework & language detection.

``FrameworkDetector`` scores every :class:`FrameworkRule` (declared in
``constants.py``) against the repository's manifest files and returns ranked
:class:`FrameworkDetection` results with confidence scores. Adding a framework
is a data change (a new rule), never a code change here — Open/Closed.

``LanguageDetector`` derives the primary/secondary languages from the scanned
file set.
"""

from __future__ import annotations

import json
import logging
import os
from collections import Counter

from app.services.repository.constants import (
    CONFIDENCE_DEPENDENCY,
    CONFIDENCE_MANIFEST_MATCH,
    CONFIDENCE_MARKER_FILE,
    FRAMEWORK_RULES,
    FrameworkRule,
)
from app.services.repository.models import FrameworkDetection, Language, ScannedFile
from app.services.repository.utils import read_text

logger = logging.getLogger(__name__)

#: Manifest files read once and shared across all rule evaluations.
_MANIFEST_FILES = (
    "package.json",
    "requirements.txt",
    "pyproject.toml",
    "Pipfile",
    "pom.xml",
    "build.gradle",
    "build.gradle.kts",
    "pubspec.yaml",
    "go.mod",
    "Cargo.toml",
)


class _ManifestBundle:
    """Lazily-read cache of root manifest files + parsed npm dependency keys."""

    def __init__(self, root: str) -> None:
        self._root = root
        self._text: dict[str, str] = {}
        self._present: set[str] = set()
        self._npm_deps: set[str] = set()
        self._python_deps: set[str] = set()
        self._load()

    def _load(self) -> None:
        try:
            entries = {e.lower(): e for e in os.listdir(self._root)}
        except OSError as exc:
            logger.warning("Could not list repository root for detection: %s", exc)
            entries = {}

        for manifest in _MANIFEST_FILES:
            actual = entries.get(manifest.lower())
            if not actual:
                continue
            self._present.add(manifest.lower())
            try:
                self._text[manifest.lower()] = read_text(
                    os.path.join(self._root, actual), sample_for_binary=0
                )
            except Exception as exc:  # detection must never crash the index run
                logger.debug("Could not read manifest %s: %s", manifest, exc)

        self._npm_deps = self._parse_package_json()
        self._python_deps = self._parse_python_manifests()

    # -- accessors ----------------------------------------------------------

    def has_file(self, name: str) -> bool:
        return name.lower() in self._present

    def text(self, name: str) -> str:
        return self._text.get(name.lower(), "")

    @property
    def npm_dependencies(self) -> set[str]:
        return self._npm_deps

    @property
    def python_dependencies(self) -> set[str]:
        return self._python_deps

    # -- parsing ------------------------------------------------------------

    def _parse_package_json(self) -> set[str]:
        raw = self.text("package.json")
        if not raw:
            return set()
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            logger.debug("package.json present but not valid JSON")
            return set()
        deps: set[str] = set()
        for key in ("dependencies", "devDependencies", "peerDependencies"):
            section = data.get(key)
            if isinstance(section, dict):
                deps.update(name.lower() for name in section)
        return deps

    def _parse_python_manifests(self) -> set[str]:
        deps: set[str] = set()
        deps.update(self._names_from_requirements(self.text("requirements.txt")))
        deps.update(self._names_from_requirements(self.text("pipfile")))
        deps.update(self._names_from_pyproject(self.text("pyproject.toml")))
        return deps

    @staticmethod
    def _names_from_requirements(raw: str) -> set[str]:
        names: set[str] = set()
        for line in raw.splitlines():
            line = line.strip()
            if not line or line.startswith("#") or line.startswith("-"):
                continue
            # Strip version specifiers / extras / markers.
            token = line.split(";")[0].strip()
            for sep in ("==", ">=", "<=", "~=", "!=", ">", "<", "[", " "):
                token = token.split(sep)[0]
            if token:
                names.add(token.strip().lower())
        return names

    @staticmethod
    def _names_from_pyproject(raw: str) -> set[str]:
        # Deliberately dependency-free: scan quoted requirement strings rather
        # than pulling in a TOML parser for a coarse presence check.
        names: set[str] = set()
        for line in raw.splitlines():
            stripped = line.strip().strip(",")
            if not (stripped.startswith('"') or stripped.startswith("'")):
                continue
            token = stripped.strip("'\"")
            for sep in ("==", ">=", "<=", "~=", "!=", ">", "<", "[", " ", "("):
                token = token.split(sep)[0]
            token = token.strip().lower()
            if token and all(c.isalnum() or c in "-_." for c in token):
                names.add(token)
        return names


class FrameworkDetector:
    """Scores framework rules against the repository manifests."""

    def __init__(self, rules: tuple[FrameworkRule, ...] = FRAMEWORK_RULES) -> None:
        self._rules = rules

    def detect(self, root: str) -> list[FrameworkDetection]:
        bundle = _ManifestBundle(root)
        detections: list[FrameworkDetection] = []

        for rule in self._rules:
            confidence, evidence = self._score(rule, bundle)
            if confidence <= 0.0:
                continue
            detections.append(
                FrameworkDetection(
                    name=rule.name,
                    category=rule.category,
                    confidence=round(min(confidence, 1.0), 3),
                    evidence=evidence,
                )
            )

        detections.sort(key=lambda d: d.confidence, reverse=True)
        if detections:
            logger.info(
                "Framework detected: %s (%.0f%% confidence)",
                detections[0].name, detections[0].confidence * 100,
            )
        else:
            logger.info("No framework detected")
        return detections

    def _score(self, rule: FrameworkRule, bundle: _ManifestBundle) -> tuple[float, list[str]]:
        confidence = 0.0
        evidence: list[str] = []

        for pkg in rule.npm_packages:
            if pkg.lower() in bundle.npm_dependencies:
                confidence = max(confidence, CONFIDENCE_DEPENDENCY)
                evidence.append(f"package.json depends on '{pkg}'")

        for pkg in rule.python_packages:
            if pkg.lower() in bundle.python_dependencies:
                confidence = max(confidence, CONFIDENCE_DEPENDENCY)
                evidence.append(f"python dependency '{pkg}'")

        for marker in rule.marker_files:
            if bundle.has_file(marker):
                confidence = max(confidence, CONFIDENCE_MARKER_FILE)
                evidence.append(f"marker file '{marker}'")

        for filename, needle in rule.manifest_contains:
            if needle.lower() in bundle.text(filename).lower():
                confidence = max(confidence, CONFIDENCE_MANIFEST_MATCH)
                evidence.append(f"'{needle}' found in {filename}")

        return confidence, evidence


#: Data/markup/doc languages that should not win "primary language" when any
#: real source code is present (a repo is not "primarily JSON").
_NON_CODE_LANGUAGES: frozenset[Language] = frozenset(
    {
        Language.JSON, Language.YAML, Language.XML, Language.TOML,
        Language.MARKDOWN, Language.HTML, Language.CSS, Language.SCSS,
    }
)


class LanguageDetector:
    """Derives primary/secondary languages from the scanned file set."""

    def breakdown(self, files: list[ScannedFile]) -> Counter[Language]:
        counts: Counter[Language] = Counter()
        for scanned in files:
            if scanned.language is not Language.UNKNOWN:
                counts[scanned.language] += 1
        return counts

    def primary_and_secondary(
        self, files: list[ScannedFile]
    ) -> tuple[Language | None, list[Language]]:
        counts = self.breakdown(files)
        if not counts:
            return None, []
        ranked = [lang for lang, _ in counts.most_common()]
        # Prefer a genuine programming language for "primary"; fall back to the
        # raw leader only when the repo contains nothing but data/markup files.
        code_ranked = [lang for lang in ranked if lang not in _NON_CODE_LANGUAGES]
        primary = code_ranked[0] if code_ranked else ranked[0]
        secondary = [lang for lang in ranked if lang != primary]
        return primary, secondary
