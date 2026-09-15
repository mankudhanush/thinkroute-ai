"""Static configuration for the Repository Intelligence Engine.

Everything that a deployment might reasonably want to tune lives here so the
rest of the module never hard-codes policy. Values are intentionally plain
data structures (sets / dicts / a frozen dataclass) so they can be imported
cheaply and overridden per-request without side effects.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

from app.services.repository.models import Language

# ---------------------------------------------------------------------------
# Traversal policy
# ---------------------------------------------------------------------------

#: Directory names pruned during traversal (never descended into).
IGNORED_DIRECTORIES: frozenset[str] = frozenset(
    {
        ".git",
        ".hg",
        ".svn",
        "node_modules",
        ".next",
        ".nuxt",
        ".svelte-kit",
        "dist",
        "build",
        "coverage",
        ".cache",
        ".parcel-cache",
        ".turbo",
        "target",
        "out",
        "bin",
        "obj",
        "venv",
        ".venv",
        "env",
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        ".tox",
        ".gradle",
        ".idea",
        ".vscode",
        ".dart_tool",
        ".angular",
        ".expo",
        "vendor",
        "Pods",
        "DerivedData",
    }
)

#: Exact file names skipped regardless of extension (lockfiles, noise).
IGNORED_FILE_NAMES: frozenset[str] = frozenset(
    {
        ".ds_store",
        "thumbs.db",
        "package-lock.json",
        "yarn.lock",
        "pnpm-lock.yaml",
        "poetry.lock",
        "pipfile.lock",
        "composer.lock",
        "cargo.lock",
    }
)

#: Extensions treated as binary/opaque — never opened or parsed.
BINARY_EXTENSIONS: frozenset[str] = frozenset(
    {
        # images
        ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ico", ".webp", ".tiff", ".svgz",
        # fonts
        ".woff", ".woff2", ".ttf", ".otf", ".eot",
        # media
        ".mp3", ".mp4", ".mov", ".avi", ".mkv", ".wav", ".flac", ".ogg", ".webm",
        # archives
        ".zip", ".tar", ".gz", ".tgz", ".rar", ".7z", ".bz2", ".xz",
        # compiled / binary artefacts
        ".pyc", ".pyo", ".so", ".dll", ".dylib", ".exe", ".bin", ".class",
        ".jar", ".war", ".o", ".a", ".lib", ".wasm", ".node",
        # documents / data blobs
        ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
        ".db", ".sqlite", ".sqlite3", ".dat", ".pack", ".idx",
    }
)

#: Maximum size (bytes) for a file to be read and parsed. Larger files are
#: recorded as skipped. 2 MiB comfortably covers source files while excluding
#: generated bundles and data dumps.
DEFAULT_MAX_FILE_SIZE_BYTES: int = 2 * 1024 * 1024

#: Bytes sampled from the head of a file when sniffing for binary content.
BINARY_SNIFF_BYTES: int = 4096

# ---------------------------------------------------------------------------
# Language mapping (extension -> Language)
# ---------------------------------------------------------------------------

LANGUAGE_BY_EXTENSION: dict[str, Language] = {
    ".py": Language.PYTHON,
    ".pyi": Language.PYTHON,
    ".js": Language.JAVASCRIPT,
    ".mjs": Language.JAVASCRIPT,
    ".cjs": Language.JAVASCRIPT,
    ".jsx": Language.JSX,
    ".ts": Language.TYPESCRIPT,
    ".mts": Language.TYPESCRIPT,
    ".cts": Language.TYPESCRIPT,
    ".tsx": Language.TSX,
    ".java": Language.JAVA,
    ".kt": Language.KOTLIN,
    ".kts": Language.KOTLIN,
    ".go": Language.GO,
    ".rs": Language.RUST,
    ".cs": Language.CSHARP,
    ".dart": Language.DART,
    ".html": Language.HTML,
    ".htm": Language.HTML,
    ".css": Language.CSS,
    ".scss": Language.SCSS,
    ".sass": Language.SCSS,
    ".less": Language.CSS,
    ".vue": Language.VUE,
    ".svelte": Language.SVELTE,
    ".json": Language.JSON,
    ".jsonc": Language.JSON,
    ".md": Language.MARKDOWN,
    ".markdown": Language.MARKDOWN,
    ".yaml": Language.YAML,
    ".yml": Language.YAML,
    ".xml": Language.XML,
    ".toml": Language.TOML,
    ".sh": Language.SHELL,
    ".bash": Language.SHELL,
    ".sql": Language.SQL,
}

#: Extensions we actively parse for structure (imports/functions/classes/etc).
#: Everything else in LANGUAGE_BY_EXTENSION is still catalogued as metadata.
PARSEABLE_LANGUAGES: frozenset[Language] = frozenset(
    {
        Language.PYTHON,
        Language.JAVASCRIPT,
        Language.JSX,
        Language.TYPESCRIPT,
        Language.TSX,
        Language.JAVA,
        Language.GO,
        Language.RUST,
        Language.CSHARP,
    }
)

# ---------------------------------------------------------------------------
# Config-file recognition
# ---------------------------------------------------------------------------

CONFIG_FILE_NAMES: frozenset[str] = frozenset(
    {
        "package.json",
        "tsconfig.json",
        "jsconfig.json",
        "next.config.js",
        "next.config.mjs",
        "next.config.ts",
        "nuxt.config.js",
        "nuxt.config.ts",
        "vite.config.js",
        "vite.config.ts",
        "webpack.config.js",
        "babel.config.js",
        ".babelrc",
        "angular.json",
        "vue.config.js",
        "tailwind.config.js",
        "tailwind.config.ts",
        "postcss.config.js",
        "requirements.txt",
        "pyproject.toml",
        "setup.py",
        "setup.cfg",
        "pipfile",
        "manage.py",
        "pom.xml",
        "build.gradle",
        "build.gradle.kts",
        "settings.gradle",
        "pubspec.yaml",
        "cargo.toml",
        "go.mod",
        "go.sum",
        "dockerfile",
        "docker-compose.yml",
        "docker-compose.yaml",
        ".env",
        ".env.example",
    }
)

# ---------------------------------------------------------------------------
# Framework detection markers
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FrameworkRule:
    """Declarative rule describing how one framework is recognised.

    Rules are intentionally data — the detector interprets them — so adding a
    new framework never touches detector logic (Open/Closed principle).
    """

    name: str
    category: str  # "frontend" | "backend" | "fullstack" | "mobile" | "language"
    #: package.json dependency keys whose presence implies this framework.
    npm_packages: tuple[str, ...] = ()
    #: Python distribution names (in requirements/pyproject) implying it.
    python_packages: tuple[str, ...] = ()
    #: Marker filenames whose mere presence is strong evidence.
    marker_files: tuple[str, ...] = ()
    #: Substrings searched inside manifest files (pom.xml, build.gradle, ...).
    manifest_contains: tuple[tuple[str, str], ...] = ()  # (filename, needle)


#: Ordered set of framework rules. Order is irrelevant to correctness — the
#: detector scores every rule and ranks by confidence.
FRAMEWORK_RULES: tuple[FrameworkRule, ...] = (
    FrameworkRule("Next.js", "fullstack", npm_packages=("next",),
                  marker_files=("next.config.js", "next.config.mjs", "next.config.ts")),
    FrameworkRule("React", "frontend", npm_packages=("react", "react-dom")),
    FrameworkRule("Vue", "frontend", npm_packages=("vue",),
                  marker_files=("vue.config.js",)),
    FrameworkRule("Angular", "frontend", npm_packages=("@angular/core",),
                  marker_files=("angular.json",)),
    FrameworkRule("Svelte", "frontend", npm_packages=("svelte",),
                  marker_files=("svelte.config.js",)),
    FrameworkRule("Express", "backend", npm_packages=("express",)),
    FrameworkRule("NestJS", "backend", npm_packages=("@nestjs/core",)),
    FrameworkRule("Node", "backend", marker_files=("package.json",)),
    FrameworkRule("FastAPI", "backend", python_packages=("fastapi",)),
    FrameworkRule("Django", "backend", python_packages=("django",),
                  marker_files=("manage.py",)),
    FrameworkRule("Flask", "backend", python_packages=("flask",)),
    FrameworkRule("Spring Boot", "backend",
                  manifest_contains=(("pom.xml", "spring-boot"),
                                     ("build.gradle", "spring-boot"),
                                     ("build.gradle.kts", "spring-boot"))),
    FrameworkRule("Flutter", "mobile", marker_files=("pubspec.yaml",),
                  manifest_contains=(("pubspec.yaml", "flutter"),)),
    FrameworkRule("Go", "language", marker_files=("go.mod",)),
    FrameworkRule("Rust", "language", marker_files=("cargo.toml",)),
)

#: Confidence contributed by each kind of evidence. Capped at 1.0 downstream.
CONFIDENCE_DEPENDENCY: float = 0.9   # named in package.json / requirements
CONFIDENCE_MARKER_FILE: float = 0.6  # config file present
CONFIDENCE_MANIFEST_MATCH: float = 0.85


@dataclass(frozen=True)
class ScanSettings:
    """Per-run traversal settings. Immutable; use :meth:`with_overrides` to
    derive a tweaked copy (e.g. a request-supplied file-size limit)."""

    max_file_size_bytes: int = DEFAULT_MAX_FILE_SIZE_BYTES
    ignore_hidden: bool = True
    follow_symlinks: bool = False
    ignored_directories: frozenset[str] = IGNORED_DIRECTORIES
    ignored_file_names: frozenset[str] = IGNORED_FILE_NAMES
    binary_extensions: frozenset[str] = BINARY_EXTENSIONS

    def with_overrides(self, **changes: object) -> "ScanSettings":
        clean = {k: v for k, v in changes.items() if v is not None}
        return replace(self, **clean) if clean else self


DEFAULT_SCAN_SETTINGS = ScanSettings()
