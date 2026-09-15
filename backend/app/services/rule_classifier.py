from __future__ import annotations

import logging
import re

from app.services.classification import ClassificationResult, enrich

logger = logging.getLogger(__name__)

# Confidence emitted for a firm rule hit. Anything at/above the router's
# threshold skips the LLM entirely; ambiguous prompts fall below it.
_STRONG = 0.95
_GOOD = 0.9

# ---------------------------------------------------------------------------
# Complexity is SEMANTIC — it reflects the effort/scope of the requested work,
# never the number of words. "Build a website" is three words but High.
# ---------------------------------------------------------------------------

# Verbs that request a whole artifact be produced from scratch.
_BUILD_VERBS = (
    "build", "create", "develop", "design", "architect", "engineer",
    "implement", "make", "generate", "code", "program", "produce", "set up",
)

# Nouns denoting a large, multi-component deliverable → High complexity.
_SYSTEM_NOUNS = (
    "website", "web site", "webapp", "web app", "application", "app",
    "system", "platform", "service", "microservice", "microservices",
    "dashboard", "engine", "framework", "pipeline", "saas", "product",
    "portal", "marketplace", "clone", "e-commerce", "ecommerce",
    "social network", "social media", "game", "chatbot", "bot",
    "builder", "management system", "crm", "erp", "backend", "full stack",
    "full-stack", "operating system", "compiler", "database system",
    "recommendation system", "search engine", "streaming",
)

# Words that signal large-scale / architectural effort → High.
_SCALE_MARKERS = (
    "scalable", "distributed", "production", "production-grade", "enterprise",
    "end-to-end", "end to end", "high availability", "fault tolerant",
    "real-time", "multi-tenant", "load balanc", "kubernetes", "cloud-native",
)

# Small, single-file artifacts → Medium (for coding).
_SMALL_ARTIFACTS = (
    "function", "program", "script", "snippet", "method", "class",
    "regex", "query", "endpoint", "api", "component", "form", "page",
    "algorithm", "cli", "command", "utility", "wrapper", "parser",
)

# Long-source nouns → the task ingests a big document (High for summarize/
# translate/analyze).
_LONG_SOURCE = (
    "paper", "research paper", "document", "article", "essay", "book",
    "chapter", "report", "thesis", "dissertation", "transcript", "pdf",
    "contract", "manuscript", "novel", "blog post", "codebase", "repository",
)

# Trivial coding markers → Low.
_TRIVIAL_CODE = ("hello world", "print statement", "one-liner", "one liner")


def _contains_any(text: str, needles: tuple[str, ...]) -> bool:
    return any(n in text for n in needles)


def _word_hit(text: str, words: tuple[str, ...]) -> bool:
    """Whole-word / phrase match so 'apple' doesn't trigger on 'app'."""
    for w in words:
        if " " in w:
            if w in text:
                return True
        elif re.search(rf"\b{re.escape(w)}\b", text):
            return True
    return False


class RuleClassifier:
    """Deterministic, sub-millisecond classifier for obvious prompts.

    Returns a high-confidence :class:`ClassificationResult` for prompts whose
    intent is unambiguous (a greeting, a "translate this", a "build a X"), so
    the qwen3:4b intent model is never invoked for the common case. Ambiguous
    prompts get a low confidence and are handed off to the LLM by the router.
    """

    # Greetings / small talk — must be the whole (short) prompt, not a
    # substring, so "hi" doesn't match "this".
    _GREETING_RE = re.compile(
        r"^(hi|hello|hey|yo|hiya|sup|howdy|good\s+(morning|afternoon|evening)|"
        r"how('?s| is| are)\b.*|what'?s up|thanks?|thank you|bye|good night)\b",
        re.IGNORECASE,
    )
    _CHITCHAT = (
        "tell me a joke", "who are you", "what can you do", "how are you",
        "your name", "make me laugh", "let's chat", "lets chat",
    )

    def classify(self, prompt: str) -> ClassificationResult:
        text = prompt.strip().lower()
        if not text:
            return enrich("general_chat", "low", _GOOD, source="rule")

        intent, complexity, confidence = self._match(text, prompt.strip())
        return enrich(intent, complexity, confidence, source="rule")

    # ------------------------------------------------------------------
    # Intent + complexity resolution. Order matters: the most specific and
    # unambiguous signals are checked first.
    # ------------------------------------------------------------------
    def _match(self, text: str, raw: str) -> tuple[str, str, float]:
        # 1. Conversation / greetings ----------------------------------
        if self._GREETING_RE.match(raw) or _contains_any(text, self._CHITCHAT):
            return "conversation", "low", _STRONG
        if len(text.split()) <= 3 and text.endswith("?") is False and not _word_hit(
            text, _SMALL_ARTIFACTS + _SYSTEM_NOUNS
        ) and _word_hit(text, ("joke", "hi", "hello", "hey", "thanks")):
            return "conversation", "low", _GOOD

        # 2. Translation ------------------------------------------------
        if _word_hit(text, ("translate", "translation")) or re.search(
            r"\b(in|to)\s+(french|spanish|german|hindi|chinese|japanese|"
            r"arabic|italian|portuguese|russian|korean)\b", text
        ):
            complexity = "high" if _word_hit(text, _LONG_SOURCE) else "low"
            return "translation", complexity, _STRONG

        # 3. Summarization ---------------------------------------------
        if _word_hit(text, ("summarize", "summarise", "summary", "tldr", "tl;dr")) or (
            "key points" in text or "main points" in text
        ):
            complexity = "high" if _word_hit(text, _LONG_SOURCE) else "medium"
            if _word_hit(text, ("sentence", "tweet", "line")):
                complexity = "low"
            return "summarization", complexity, _STRONG

        # 4. Debugging --------------------------------------------------
        if _word_hit(text, ("debug", "traceback", "stack trace", "stacktrace")) or (
            _word_hit(text, ("fix", "solve", "resolve"))
            and _word_hit(text, ("bug", "error", "issue", "exception", "crash",
                                  "not working", "broken", "fails", "failing"))
        ) or re.search(r"why (is|does|isn'?t|doesn'?t).*(not work|error|fail|break)", text):
            # Debugging is Low unless it's a whole-system/production problem.
            complexity = "high" if _contains_any(text, _SCALE_MARKERS) else "low"
            if _word_hit(text, ("across", "entire", "whole", "multiple")):
                complexity = "medium"
            return "debugging", complexity, _GOOD

        # 5. Creative writing ------------------------------------------
        if _word_hit(text, ("story", "poem", "poetry", "haiku", "novel", "song",
                            "lyrics", "screenplay", "script", "fiction", "essay")) and \
                _word_hit(text, ("write", "compose", "create", "generate", "tell")):
            if _word_hit(text, ("novel", "book", "screenplay", "chapter", "saga")):
                complexity = "high"
            elif _word_hit(text, ("haiku", "tweet", "one-liner", "limerick")):
                complexity = "low"
            else:
                complexity = "medium"
            return "creative_writing", complexity, _GOOD

        # 6. Mathematics ------------------------------------------------
        if _word_hit(text, ("integral", "derivative", "equation", "theorem",
                            "probability", "matrix", "calculus", "algebra",
                            "prove", "proof")) or re.search(r"\d\s*[\+\-\*/x=]\s*\d", text):
            complexity = "high" if _word_hit(text, ("prove", "proof", "theorem")) else "medium"
            if re.fullmatch(r"[\d\s\+\-\*/x=().]+\??", text):
                complexity = "low"
            return "mathematics", complexity, _GOOD

        # 7. Research ---------------------------------------------------
        if _word_hit(text, ("research", "literature review", "investigate",
                            "state of the art", "survey the", "find sources")):
            return "research", "high", _GOOD

        # 8. Reasoning / system design ---------------------------------
        if _word_hit(text, ("architecture", "microservices", "system design")) or (
            _word_hit(text, ("design", "architect"))
            and _word_hit(text, ("scalable", "distributed", "architecture", "system"))
        ) or _word_hit(text, ("trade-off", "tradeoff", "logic puzzle")):
            return "reasoning", "high", _GOOD

        # 9. Coding -----------------------------------------------------
        code_langs = (
            "python", "java", "javascript", "typescript", "react", "node",
            "nextjs", "next.js", "c++", "c#", "golang", "rust", "sql", "html",
            "css", "php", "ruby", "swift", "kotlin", "flask", "django",
            "fastapi", "express", "spring", "angular", "vue", "tailwind",
        )
        looks_like_code = (
            _word_hit(text, code_langs)
            or _word_hit(text, _SMALL_ARTIFACTS)
            or (_word_hit(text, _BUILD_VERBS) and _word_hit(text, _SYSTEM_NOUNS))
        )
        if looks_like_code:
            complexity = self._code_complexity(text)
            return "coding", complexity, _GOOD

        # 10. Education -------------------------------------------------
        if _word_hit(text, ("explain", "teach", "understand", "concept", "learn")) or \
                re.match(r"^(what|how|why|when)\b.*(is|are|does|do|work|mean)", text):
            complexity = "high" if _word_hit(text, ("in depth", "in-depth",
                                                    "comprehensive", "advanced")) else "medium"
            return "education", complexity, _GOOD

        # No firm rule matched → low confidence, defer to the intent model.
        return "general_chat", "medium", 0.3

    def _code_complexity(self, text: str) -> str:
        """Semantic complexity for a coding task — scope, not length."""
        if _contains_any(text, _TRIVIAL_CODE):
            return "low"
        # A build verb aimed at a whole system, or any scale marker → High.
        if _contains_any(text, _SCALE_MARKERS):
            return "high"
        if _word_hit(text, _BUILD_VERBS) and _word_hit(text, _SYSTEM_NOUNS):
            return "high"
        if _word_hit(text, _SYSTEM_NOUNS) and not _word_hit(text, _SMALL_ARTIFACTS):
            return "high"
        # Single-artifact requests → Medium.
        if _word_hit(text, _SMALL_ARTIFACTS):
            return "medium"
        return "medium"
