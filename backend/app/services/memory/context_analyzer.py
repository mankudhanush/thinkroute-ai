from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.services.memory import similarity

# Phrases that reference prior work but carry NO new topic of their own.
# These force the prompt onto the most recent active thread.
_PURE_REFERENCE = (
    "continue", "go on", "keep going", "carry on", "proceed", "next",
    "do the same", "same thing", "same as before", "again", "one more",
    "and", "more", "go ahead",
)

# Phrases that signal a follow-up/refinement of existing work. They usually
# carry a small new instruction ("add authentication") but still attach to the
# current thread.
_FOLLOWUP_MARKERS = (
    "continue", "do the same", "improve it", "improve this", "make it better",
    "fix it", "fix this", "expand it", "expand this", "optimize it",
    "optimize this", "refactor it", "refactor this", "add ", "also add",
    "now add", "now create", "now generate", "now build", "now make",
    "now implement", "implement ", "generate backend", "generate frontend",
    "create frontend", "create backend", "deploy it", "deploy this",
    "update it", "change it", "enhance it", "extend it", "same but",
    "and also", "next step", "keep the", "based on that", "using that",
)

# Openers that usually START a brand-new, self-contained topic.
_NEW_TOPIC_MARKERS = (
    "explain", "what is", "what are", "tell me about", "define", "compare",
    "difference between", "how does", "how do", "who is", "give me a joke",
    "tell me a joke", "translate", "summarize", "summarise",
)


@dataclass(frozen=True)
class PromptAnalysis:
    is_followup: bool
    is_pure_reference: bool
    likely_new_topic: bool
    matched_markers: tuple[str, ...]
    keywords: set[str] = field(default_factory=set)
    topic_keywords: set[str] = field(default_factory=set)
    word_count: int = 0


class ContextAnalyzer:
    """Analyses the CURRENT prompt only (no history) — pure string work, well
    under a millisecond. Decides whether the prompt is a follow-up, a bare
    reference ("continue"), or the likely start of a new topic, and extracts
    keywords for downstream thread matching + retrieval.
    """

    def analyze(self, prompt: str) -> PromptAnalysis:
        text = prompt.strip().lower()
        words = text.split()
        wc = len(words)

        matched = tuple(m for m in _FOLLOWUP_MARKERS if m in text)

        # A pure reference is a short prompt that is essentially just a
        # reference phrase ("continue", "do the same", "go on").
        stripped = re.sub(r"[^a-z ]", "", text).strip()
        is_pure_reference = wc <= 3 and any(
            stripped == p or stripped.startswith(p + " ") or stripped == p.replace(" ", "")
            for p in _PURE_REFERENCE
        )

        topic_kw = similarity.keywords(prompt, drop_followup_noise=True)
        all_kw = similarity.keywords(prompt)

        # New topic if it opens with a topic marker AND isn't a follow-up phrase.
        likely_new_topic = (
            any(text.startswith(m) or f" {m}" in f" {text}" for m in _NEW_TOPIC_MARKERS)
            and not matched
        )

        is_followup = bool(matched) or is_pure_reference

        return PromptAnalysis(
            is_followup=is_followup,
            is_pure_reference=is_pure_reference,
            likely_new_topic=likely_new_topic,
            matched_markers=matched,
            keywords=all_kw,
            topic_keywords=topic_kw,
            word_count=wc,
        )
