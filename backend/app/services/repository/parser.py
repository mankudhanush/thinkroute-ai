"""Language parsers.

Design goals:
  * **AST first.** Python is parsed with the standard-library ``ast`` module —
    no regex, exact line spans, decorators, async, class methods.
  * **Production-grade, pluggable JS/TS.** The JavaScript/TypeScript parser
    delegates to a :class:`JsSymbolBackend`. If the optional ``tree-sitter``
    grammars are installed they are used automatically; otherwise a robust,
    well-scoped heuristic backend runs so the module is fully functional with
    zero extra dependencies. Installing ``tree-sitter-languages`` upgrades the
    JS/TS path transparently — no calling code changes.
  * **Extensible.** New languages register a parser in :class:`ParserRegistry`.
    Every parser returns the same :class:`Extraction` shape, so the aggregator
    and all future phases stay language-agnostic.

Parsers never raise on malformed input — they capture the problem in
``Extraction.error`` and return whatever was recovered, so one bad file can
never abort indexing a 100k-file repository.
"""

from __future__ import annotations

import ast
import logging
import re
from dataclasses import dataclass, field
from typing import Protocol

from app.services.repository.models import (
    ClassMetadata,
    ComponentMetadata,
    ExportMetadata,
    FunctionMetadata,
    ImportMetadata,
    Language,
    ScannedFile,
    SymbolKind,
    SymbolMetadata,
)

logger = logging.getLogger(__name__)


@dataclass
class Extraction:
    """Language-agnostic bundle of symbols recovered from one file."""

    imports: list[ImportMetadata] = field(default_factory=list)
    exports: list[ExportMetadata] = field(default_factory=list)
    functions: list[FunctionMetadata] = field(default_factory=list)
    classes: list[ClassMetadata] = field(default_factory=list)
    components: list[ComponentMetadata] = field(default_factory=list)
    hooks: list[str] = field(default_factory=list)
    interfaces: list[SymbolMetadata] = field(default_factory=list)
    types: list[SymbolMetadata] = field(default_factory=list)
    enums: list[SymbolMetadata] = field(default_factory=list)
    decorators: list[str] = field(default_factory=list)
    async_functions: list[str] = field(default_factory=list)
    error: str | None = None


class FileParser(Protocol):
    """Contract every language parser implements."""

    def extract(self, scanned: ScannedFile, text: str) -> Extraction: ...


# ---------------------------------------------------------------------------
# Python — true AST parsing
# ---------------------------------------------------------------------------


class PythonAstParser:
    """Extracts structure from Python via the standard-library AST."""

    def extract(self, scanned: ScannedFile, text: str) -> Extraction:
        result = Extraction()
        try:
            tree = ast.parse(text)
        except SyntaxError as exc:
            result.error = f"Python syntax error: {exc.msg} (line {exc.lineno})"
            return result

        exported_all = self._dunder_all(tree)
        for node in tree.body:  # module-level only; methods live under classes
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                result.imports.extend(self._imports(node))
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                result.functions.append(self._function(node, is_method=False))
            elif isinstance(node, ast.ClassDef):
                result.classes.append(self._class(node))

        self._collect_async_and_decorators(tree, result)
        self._mark_exports(result, exported_all)
        return result

    # -- node builders ------------------------------------------------------

    @staticmethod
    def _imports(node: ast.Import | ast.ImportFrom) -> list[ImportMetadata]:
        if isinstance(node, ast.Import):
            return [
                ImportMetadata(
                    module=alias.name,
                    alias=alias.asname,
                    is_relative=False,
                    is_external=True,
                    line=node.lineno,
                    raw=f"import {alias.name}",
                )
                for alias in node.names
            ]
        module = node.module or ""
        is_relative = node.level > 0
        return [
            ImportMetadata(
                module=module,
                names=[a.name for a in node.names],
                is_relative=is_relative,
                is_external=not is_relative,
                level=node.level,
                line=node.lineno,
                raw=f"from {'.' * node.level}{module} import ...",
            )
        ]

    def _function(self, node: ast.FunctionDef | ast.AsyncFunctionDef, *, is_method: bool) -> FunctionMetadata:
        return FunctionMetadata(
            name=node.name,
            is_async=isinstance(node, ast.AsyncFunctionDef),
            is_method=is_method,
            decorators=[self._unparse(d) for d in node.decorator_list],
            parameters=self._parameters(node.args),
            returns=self._unparse(node.returns) if node.returns else None,
            line_start=node.lineno,
            line_end=getattr(node, "end_lineno", node.lineno) or node.lineno,
        )

    def _class(self, node: ast.ClassDef) -> ClassMetadata:
        methods = [
            self._function(item, is_method=True)
            for item in node.body
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
        ]
        return ClassMetadata(
            name=node.name,
            bases=[self._unparse(b) for b in node.bases],
            decorators=[self._unparse(d) for d in node.decorator_list],
            methods=methods,
            line_start=node.lineno,
            line_end=getattr(node, "end_lineno", node.lineno) or node.lineno,
        )

    @staticmethod
    def _parameters(args: ast.arguments) -> list[str]:
        collected = [a.arg for a in (*args.posonlyargs, *args.args, *args.kwonlyargs)]
        if args.vararg:
            collected.append(f"*{args.vararg.arg}")
        if args.kwarg:
            collected.append(f"**{args.kwarg.arg}")
        return collected

    @staticmethod
    def _unparse(node: ast.AST) -> str:
        try:
            return ast.unparse(node)
        except Exception:  # extremely rare; never fail a parse over cosmetics
            return type(node).__name__

    @staticmethod
    def _dunder_all(tree: ast.Module) -> set[str]:
        for node in tree.body:
            if isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == "__all__" for t in node.targets
            ):
                if isinstance(node.value, (ast.List, ast.Tuple)):
                    return {
                        el.value for el in node.value.elts
                        if isinstance(el, ast.Constant) and isinstance(el.value, str)
                    }
        return set()

    def _collect_async_and_decorators(self, tree: ast.Module, result: Extraction) -> None:
        decorators: set[str] = set()
        async_names: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.AsyncFunctionDef):
                async_names.append(node.name)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                decorators.update(self._unparse(d) for d in node.decorator_list)
        result.async_functions = async_names
        result.decorators = sorted(decorators)

    @staticmethod
    def _mark_exports(result: Extraction, dunder_all: set[str]) -> None:
        # Python has no export keyword: public top-level defs/classes (or an
        # explicit __all__) are the module's exported surface.
        for fn in result.functions:
            exported = fn.name in dunder_all if dunder_all else not fn.name.startswith("_")
            fn.is_exported = exported
            if exported:
                result.exports.append(ExportMetadata(name=fn.name, kind=SymbolKind.FUNCTION, line=fn.line_start))
        for cls in result.classes:
            exported = cls.name in dunder_all if dunder_all else not cls.name.startswith("_")
            cls.is_exported = exported
            if exported:
                result.exports.append(ExportMetadata(name=cls.name, kind=SymbolKind.CLASS, line=cls.line_start))


# ---------------------------------------------------------------------------
# JavaScript / TypeScript — pluggable backend (tree-sitter → heuristic)
# ---------------------------------------------------------------------------


class JsSymbolBackend(Protocol):
    def parse(self, scanned: ScannedFile, text: str) -> Extraction: ...


_IMPORT_FROM = re.compile(r"""^\s*import\s+(?:type\s+)?(?P<clause>.+?)\s+from\s+['"](?P<mod>[^'"]+)['"]""")
_IMPORT_SIDE = re.compile(r"""^\s*import\s+['"](?P<mod>[^'"]+)['"]""")
_REQUIRE = re.compile(r"""require\(\s*['"](?P<mod>[^'"]+)['"]\s*\)""")
_EXPORT_NAMED = re.compile(r"""^\s*export\s+(?P<default>default\s+)?(?:async\s+)?(?:function|class|const|let|var)\s+(?P<name>[A-Za-z0-9_$]+)""")
_EXPORT_DEFAULT_ID = re.compile(r"""^\s*export\s+default\s+(?P<name>[A-Za-z0-9_$]+)\s*;?\s*$""")
_EXPORT_BRACE = re.compile(r"""^\s*export\s*\{(?P<names>[^}]+)\}""")
_FUNC_DECL = re.compile(r"""^\s*(?P<export>export\s+)?(?:default\s+)?(?P<async>async\s+)?function\s*\*?\s*(?P<name>[A-Za-z0-9_$]+)""")
_ARROW_DECL = re.compile(r"""^\s*(?P<export>export\s+)?(?:default\s+)?(?:const|let|var)\s+(?P<name>[A-Za-z0-9_$]+)\s*(?::[^=]+)?=\s*(?P<async>async\s+)?(?P<params>\([^)]*\)|[A-Za-z0-9_$]+)\s*=>""")
_CLASS_DECL = re.compile(r"""^\s*(?P<export>export\s+)?(?:default\s+)?(?:abstract\s+)?class\s+(?P<name>[A-Za-z0-9_$]+)""")
_INTERFACE_DECL = re.compile(r"""^\s*(?P<export>export\s+)?interface\s+(?P<name>[A-Za-z0-9_$]+)""")
_TYPE_DECL = re.compile(r"""^\s*(?P<export>export\s+)?type\s+(?P<name>[A-Za-z0-9_$]+)\s*[=<]""")
_ENUM_DECL = re.compile(r"""^\s*(?P<export>export\s+)?(?:const\s+)?enum\s+(?P<name>[A-Za-z0-9_$]+)""")
_HOOK_CALL = re.compile(r"""\b(?P<hook>use[A-Z][A-Za-z0-9_$]*)\s*\(""")
_DECORATOR = re.compile(r"""^\s*@(?P<name>[A-Za-z0-9_$.]+)""")


class HeuristicJsBackend:
    """Line-oriented JS/TS extractor.

    Not a full AST, but deliberately conservative: it anchors on statement
    starts and paired quotes rather than trying to understand expressions, so
    it is stable across the language's surface syntax. Used automatically when
    tree-sitter grammars are not installed.
    """

    def parse(self, scanned: ScannedFile, text: str) -> Extraction:
        result = Extraction()
        is_jsx = scanned.language in (Language.JSX, Language.TSX)
        hooks: set[str] = set()

        for lineno, raw_line in enumerate(text.splitlines(), start=1):
            line = raw_line.rstrip()
            self._imports(line, lineno, result)
            self._exports(line, lineno, result)
            self._functions(line, lineno, result, is_jsx)
            self._classes(line, lineno, result)
            self._type_symbols(line, lineno, result)
            self._decorators(line, result)
            hooks.update(m.group("hook") for m in _HOOK_CALL.finditer(line))

        result.hooks = sorted(hooks)
        return result

    # -- per-line handlers --------------------------------------------------

    def _imports(self, line: str, lineno: int, result: Extraction) -> None:
        m = _IMPORT_FROM.match(line)
        if m:
            result.imports.append(self._import(m.group("mod"), lineno, line, m.group("clause")))
            return
        m = _IMPORT_SIDE.match(line)
        if m:
            result.imports.append(self._import(m.group("mod"), lineno, line, ""))
            return
        for req in _REQUIRE.finditer(line):
            result.imports.append(self._import(req.group("mod"), lineno, line, ""))

    @staticmethod
    def _import(module: str, lineno: int, raw: str, clause: str) -> ImportMetadata:
        is_relative = module.startswith(".") or module.startswith("/")
        names = [n.strip() for n in re.sub(r"[{}]", "", clause).split(",") if n.strip()] if clause else []
        return ImportMetadata(
            module=module, names=names, is_relative=is_relative,
            is_external=not is_relative, line=lineno, raw=raw.strip(),
        )

    @staticmethod
    def _exports(line: str, lineno: int, result: Extraction) -> None:
        m = _EXPORT_NAMED.match(line)
        if m:
            result.exports.append(
                ExportMetadata(name=m.group("name"), is_default=bool(m.group("default")), line=lineno)
            )
        m = _EXPORT_DEFAULT_ID.match(line)
        if m:
            result.exports.append(ExportMetadata(name=m.group("name"), is_default=True, line=lineno))
        m = _EXPORT_BRACE.match(line)
        if m:
            for name in m.group("names").split(","):
                cleaned = name.split(" as ")[0].strip()
                if cleaned:
                    result.exports.append(ExportMetadata(name=cleaned, line=lineno))

    def _functions(self, line: str, lineno: int, result: Extraction, is_jsx: bool) -> None:
        m = _FUNC_DECL.match(line)
        if m:
            self._add_function(m, lineno, result, is_jsx)
            return
        m = _ARROW_DECL.match(line)
        if m:
            self._add_function(m, lineno, result, is_jsx)

    @staticmethod
    def _add_function(match: re.Match[str], lineno: int, result: Extraction, is_jsx: bool) -> None:
        name = match.group("name")
        is_async = bool(match.groupdict().get("async"))
        exported = bool(match.groupdict().get("export"))
        fn = FunctionMetadata(
            name=name, is_async=is_async, is_exported=exported,
            line_start=lineno, line_end=lineno,
        )
        result.functions.append(fn)
        if is_async:
            result.async_functions.append(name)
        # A capitalised declaration in a JSX/TSX file is treated as a component.
        if is_jsx and name[:1].isupper():
            result.components.append(
                ComponentMetadata(name=name, kind="function", is_exported=exported, line=lineno)
            )

    @staticmethod
    def _classes(line: str, lineno: int, result: Extraction) -> None:
        m = _CLASS_DECL.match(line)
        if m:
            result.classes.append(
                ClassMetadata(name=m.group("name"), is_exported=bool(m.group("export")),
                              line_start=lineno, line_end=lineno)
            )

    @staticmethod
    def _type_symbols(line: str, lineno: int, result: Extraction) -> None:
        for regex, bucket, kind in (
            (_INTERFACE_DECL, result.interfaces, SymbolKind.INTERFACE),
            (_TYPE_DECL, result.types, SymbolKind.TYPE),
            (_ENUM_DECL, result.enums, SymbolKind.ENUM),
        ):
            m = regex.match(line)
            if m:
                bucket.append(
                    SymbolMetadata(name=m.group("name"), kind=kind,
                                   is_exported=bool(m.group("export")), line=lineno)
                )

    @staticmethod
    def _decorators(line: str, result: Extraction) -> None:
        m = _DECORATOR.match(line)
        if m and m.group("name") not in result.decorators:
            result.decorators.append(m.group("name"))


def _load_tree_sitter_backend() -> JsSymbolBackend | None:
    """Return a tree-sitter backend if the optional grammars are importable.

    Kept intentionally lazy and fully guarded: any import/initialisation issue
    degrades to the heuristic backend rather than breaking the module.
    """
    try:
        from app.services.repository._tree_sitter_backend import TreeSitterJsBackend
    except Exception:  # module or grammars absent
        return None
    try:
        return TreeSitterJsBackend()
    except Exception as exc:  # grammar build/load failure
        logger.info("tree-sitter unavailable, using heuristic JS/TS parser (%s)", exc)
        return None


class JsTsParser:
    """JS/TS/JSX/TSX parser that prefers tree-sitter and falls back cleanly."""

    def __init__(self, backend: JsSymbolBackend | None = None) -> None:
        self._backend = backend or _load_tree_sitter_backend() or HeuristicJsBackend()
        logger.debug("JsTsParser backend: %s", type(self._backend).__name__)

    def extract(self, scanned: ScannedFile, text: str) -> Extraction:
        try:
            return self._backend.parse(scanned, text)
        except Exception as exc:  # never let a parser bug abort indexing
            logger.warning("JS/TS parse failed for %s: %s", scanned.relative_path, exc)
            return Extraction(error=f"js/ts parse error: {exc}")


# ---------------------------------------------------------------------------
# Generic C-family heuristic parser (Java / Go / Rust / C#)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CFamilyRules:
    import_patterns: tuple[re.Pattern[str], ...]
    class_patterns: tuple[re.Pattern[str], ...]
    function_patterns: tuple[re.Pattern[str], ...]


_C_FAMILY: dict[Language, CFamilyRules] = {
    Language.JAVA: CFamilyRules(
        import_patterns=(re.compile(r"^\s*import\s+(?:static\s+)?(?P<mod>[\w.]+)\s*;"),),
        class_patterns=(re.compile(r"^\s*(?:public|private|protected)?\s*(?:final\s+|abstract\s+)?(?:class|interface|enum)\s+(?P<name>\w+)"),),
        function_patterns=(re.compile(r"^\s*(?:public|private|protected)\s+(?:static\s+)?[\w<>\[\]]+\s+(?P<name>\w+)\s*\("),),
    ),
    Language.GO: CFamilyRules(
        import_patterns=(re.compile(r'^\s*(?:import\s+)?"(?P<mod>[^"]+)"'),),
        class_patterns=(re.compile(r"^\s*type\s+(?P<name>\w+)\s+(?:struct|interface)"),),
        function_patterns=(re.compile(r"^\s*func\s+(?:\([^)]*\)\s*)?(?P<name>\w+)\s*\("),),
    ),
    Language.RUST: CFamilyRules(
        import_patterns=(re.compile(r"^\s*use\s+(?P<mod>[\w:]+)"),),
        class_patterns=(re.compile(r"^\s*(?:pub\s+)?(?:struct|enum|trait)\s+(?P<name>\w+)"),),
        function_patterns=(re.compile(r"^\s*(?:pub\s+)?(?:async\s+)?fn\s+(?P<name>\w+)\s*"),),
    ),
    Language.CSHARP: CFamilyRules(
        import_patterns=(re.compile(r"^\s*using\s+(?:static\s+)?(?P<mod>[\w.]+)\s*;"),),
        class_patterns=(re.compile(r"^\s*(?:public|private|protected|internal)?\s*(?:sealed\s+|abstract\s+|static\s+)?(?:class|interface|struct|enum)\s+(?P<name>\w+)"),),
        function_patterns=(re.compile(r"^\s*(?:public|private|protected|internal)\s+(?:static\s+|async\s+|virtual\s+|override\s+)*[\w<>\[\]]+\s+(?P<name>\w+)\s*\("),),
    ),
}


class CFamilyHeuristicParser:
    """Shared line-based parser for Java/Go/Rust/C# imports & definitions."""

    def __init__(self, rules: CFamilyRules) -> None:
        self._rules = rules

    def extract(self, scanned: ScannedFile, text: str) -> Extraction:
        result = Extraction()
        for lineno, raw in enumerate(text.splitlines(), start=1):
            line = raw.rstrip()
            for pattern in self._rules.import_patterns:
                m = pattern.match(line)
                if m:
                    module = m.group("mod")
                    result.imports.append(
                        ImportMetadata(module=module, is_relative=module.startswith("."),
                                       is_external=not module.startswith("."), line=lineno, raw=line.strip())
                    )
            for pattern in self._rules.class_patterns:
                m = pattern.match(line)
                if m:
                    result.classes.append(ClassMetadata(name=m.group("name"), line_start=lineno, line_end=lineno))
            for pattern in self._rules.function_patterns:
                m = pattern.match(line)
                if m:
                    is_async = "async" in line
                    fn = FunctionMetadata(name=m.group("name"), is_async=is_async, line_start=lineno, line_end=lineno)
                    result.functions.append(fn)
                    if is_async:
                        result.async_functions.append(fn.name)
        return result


class NullParser:
    """No-op parser for catalogued-only files (markup/data/docs)."""

    def extract(self, scanned: ScannedFile, text: str) -> Extraction:
        return Extraction()


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


class ParserRegistry:
    """Maps a :class:`Language` to its parser. Register once, reuse per run.

    New languages plug in here without touching the aggregator or router —
    exactly the extension seam later phases (and new grammars) rely on.
    """

    def __init__(self) -> None:
        js = JsTsParser()  # backend resolved once (tree-sitter probe is cached)
        self._null = NullParser()
        self._parsers: dict[Language, FileParser] = {
            Language.PYTHON: PythonAstParser(),
            Language.JAVASCRIPT: js,
            Language.JSX: js,
            Language.TYPESCRIPT: js,
            Language.TSX: js,
        }
        for language, rules in _C_FAMILY.items():
            self._parsers[language] = CFamilyHeuristicParser(rules)

    def get(self, language: Language) -> FileParser:
        return self._parsers.get(language, self._null)

    def parse(self, scanned: ScannedFile, text: str) -> Extraction:
        return self.get(scanned.language).extract(scanned, text)
