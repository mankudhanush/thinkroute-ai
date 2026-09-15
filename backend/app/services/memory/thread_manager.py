from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.services.memory import similarity
from app.services.memory.context_analyzer import ContextAnalyzer, PromptAnalysis

# ── Coarse conversational domains ──────────────────────────────────────────
# Threading first separates by domain so a software project never merges with
# an "explain X" aside, then refines within a domain by keyword similarity.
_KNOWLEDGE_OPENERS = (
    "explain", "what is", "what are", "what's", "define", "describe",
    "compare", "difference between", "how does", "how do", "why does",
    "why is", "who is", "who was", "tell me about", "teach me",
)
_SOFTWARE_MARKERS = (
    # languages / frameworks
    "python", "java", "javascript", "typescript", "react", "node", "next.js",
    "nextjs", "c++", "c#", "golang", "rust", "sql", "html", "css", "php",
    "django", "flask", "fastapi", "express", "spring", "angular", "vue",
    # artifacts / concepts
    "api", "endpoint", "function", "class", "script", "program", "component",
    "frontend", "backend", "server", "client", "database", "db", "schema",
    "diagram", "er ", "table", "auth", "authentication", "login", "signup",
    "dashboard", "payment", "gateway", "navbar", "ui", "button", "form",
    "deploy", "docker", "kubernetes", "microservice", "website", "web app",
    "webapp", "app", "application", "system", "platform", "crud", "route",
)
_DEBUG_MARKERS = ("fix", "debug", "bug", "error", "exception", "crash", "broken", "not working")
_TRANSLATE_MARKERS = ("translate", "translation")
_DOC_MARKERS = ("summarize", "summarise", "summary", "tldr", "tl;dr")
_CREATIVE_MARKERS = ("story", "poem", "poetry", "haiku", "song", "lyrics", "novel", "screenplay")

# Verbs that continue/extend prior work (attach to the active thread).
_CONTINUATION_VERBS = (
    "add", "also", "now", "continue", "fix", "improve", "expand", "optimize",
    "refactor", "update", "change", "generate", "create", "build", "develop",
    "design", "implement", "deploy", "make", "extend", "enhance", "integrate",
)

_GREETING_RE = re.compile(r"^(hi|hello|hey|yo|thanks|thank you|bye)\b", re.IGNORECASE)


def _domain(text: str) -> str:
    t = text.strip().lower()
    if not t:
        return "general"
    if _GREETING_RE.match(t):
        return "chat"
    # Explicit "explain/compare/what is" openers are knowledge even if they
    # mention a language ("Compare Python vs Java" is a knowledge question).
    if any(t.startswith(o) or f" {o}" in f" {t}" for o in _KNOWLEDGE_OPENERS):
        return "knowledge"
    if any(m in t for m in _TRANSLATE_MARKERS):
        return "translation"
    if any(m in t for m in _DOC_MARKERS):
        return "documents"
    if any(re.search(rf"\b{re.escape(m)}\b", t) for m in _CREATIVE_MARKERS):
        return "creative"
    if any(m in t for m in _SOFTWARE_MARKERS) or any(re.search(rf"\b{re.escape(m)}\b", t) for m in _DEBUG_MARKERS):
        return "software"
    return "general"


def _starts_with_continuation(text: str) -> bool:
    t = text.strip().lower()
    first = t.split()[0] if t.split() else ""
    return first in _CONTINUATION_VERBS


@dataclass
class Thread:
    thread_id: str
    domain: str
    message_indices: list[int] = field(default_factory=list)  # all history rows (user+assistant)
    user_indices: list[int] = field(default_factory=list)     # user rows only (topic anchors)
    keywords: set[str] = field(default_factory=set)
    last_index: int = -1

    def add(self, index: int, *, is_user: bool, kw: set[str]) -> None:
        self.message_indices.append(index)
        self.last_index = index
        if is_user:
            self.user_indices.append(index)
            self.keywords |= kw


@dataclass
class ThreadView:
    threads: list[Thread]
    current_thread_id: str | None
    by_id: dict[str, Thread]


# Keyword similarity needed to join an existing same-domain thread.
_JOIN_THRESHOLD = 0.18
# Higher bar for an explicit new-topic opener to re-join an old thread.
_REJOIN_THRESHOLD = 0.5


class ThreadManager:
    """Groups a conversation into logical threads and decides which thread a
    new prompt belongs to. Deterministic and dependency-free.
    """

    def __init__(self, analyzer: ContextAnalyzer, scorer: similarity.SimilarityScorer) -> None:
        self.analyzer = analyzer
        self.scorer = scorer

    # ------------------------------------------------------------------
    def reconstruct(self, history: list[dict]) -> ThreadView:
        """Rebuild threads by replaying the assignment rule over history.

        Resilient to legacy rows without a stored thread_id — grouping is
        derived from message content, so it works on any conversation.
        """
        threads: list[Thread] = []
        by_id: dict[str, Thread] = {}
        current: Thread | None = None
        counter = 0

        for idx, msg in enumerate(history):
            role = msg.get("role")
            content = msg.get("content") or ""
            if role == "assistant":
                # Assistant replies belong to the active thread's turn.
                if current is not None:
                    current.add(idx, is_user=False, kw=set())
                continue

            analysis = self.analyzer.analyze(content)
            domain = self._effective_domain(content, current)
            target = self._pick_thread(threads, current, analysis, domain, content)

            if target is None:
                counter += 1
                target = Thread(thread_id=f"t{counter}", domain=domain)
                threads.append(target)
                by_id[target.thread_id] = target

            target.add(idx, is_user=True, kw=analysis.topic_keywords)
            current = target

        return ThreadView(threads=threads, current_thread_id=(current.thread_id if current else None), by_id=by_id)

    # ------------------------------------------------------------------
    def assign(self, view: ThreadView, prompt: str, analysis: PromptAnalysis) -> tuple[str, bool, str]:
        """Decide the thread for the NEW prompt. Returns (thread_id, is_new, domain)."""
        current = view.by_id.get(view.current_thread_id) if view.current_thread_id else None
        domain = self._effective_domain(prompt, current)
        target = self._pick_thread(view.threads, current, analysis, domain, prompt)
        if target is not None:
            return target.thread_id, False, domain
        # New thread id continues the deterministic sequence.
        new_id = f"t{len(view.threads) + 1}"
        return new_id, True, domain

    # ------------------------------------------------------------------
    def _effective_domain(self, text: str, current: Thread | None) -> str:
        domain = _domain(text)
        # A bare continuation with no domain signal inherits the active thread's
        # domain ("Add authentication" continues the software project).
        if domain in ("general", "chat") and current is not None and _starts_with_continuation(text):
            return current.domain
        return domain

    def _pick_thread(
        self,
        threads: list[Thread],
        current: Thread | None,
        analysis: PromptAnalysis,
        domain: str,
        text: str,
    ) -> Thread | None:
        if not threads:
            return None

        # Bare references ("continue", "do the same") stick to the active thread.
        if analysis.is_pure_reference and current is not None:
            return current

        same_domain = [t for t in threads if t.domain == domain]
        if not same_domain:
            return None  # different domain → start a new thread

        best = max(same_domain, key=lambda t: self.scorer.score_keywords(analysis.topic_keywords, t.keywords))
        best_score = self.scorer.score_keywords(analysis.topic_keywords, best.keywords)

        # Follow-ups / continuations extend the active thread when it shares the
        # domain, otherwise the best-matching same-domain thread.
        if analysis.is_followup or _starts_with_continuation(text):
            if current is not None and current.domain == domain:
                return current
            return best

        # An explicit new-topic opener only re-joins an old thread on a strong
        # keyword match; otherwise it starts fresh.
        if analysis.likely_new_topic:
            return best if best_score >= _REJOIN_THRESHOLD else None

        return best if best_score >= _JOIN_THRESHOLD else None
