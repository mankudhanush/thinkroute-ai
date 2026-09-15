from __future__ import annotations

import math
import re
from collections import Counter

# Lightweight, dependency-free text similarity. The public surface is a
# SimilarityScorer protocol so a vector/embedding scorer can be dropped in
# later WITHOUT changing any caller (thread manager, retriever, engine).

_STOPWORDS = frozenset({
    "a", "an", "the", "and", "or", "but", "if", "then", "else", "for", "to",
    "of", "in", "on", "at", "by", "with", "from", "as", "is", "are", "was",
    "were", "be", "been", "being", "this", "that", "these", "those", "it",
    "its", "i", "you", "he", "she", "we", "they", "me", "my", "your", "our",
    "do", "does", "did", "can", "could", "should", "would", "will", "shall",
    "please", "now", "also", "just", "so", "very", "some", "any", "all",
    "how", "what", "why", "when", "which", "who", "whom", "here", "there",
    "about", "into", "up", "down", "out", "over", "again", "more", "most",
    "let", "lets", "make", "get", "got", "want", "need", "give", "us",
})

# Common follow-up verbs are deliberately NOT stopwords — but they carry no
# *topic* signal, so we drop them when extracting topic keywords.
_FOLLOWUP_NOISE = frozenset({
    "continue", "add", "fix", "improve", "expand", "optimize", "generate",
    "create", "build", "implement", "deploy", "refactor", "update", "change",
    "same", "it", "this", "that", "them", "again",
})

_TOKEN_RE = re.compile(r"[a-z0-9+#.]+")


def tokenize(text: str) -> list[str]:
    """Lowercase word/identifier tokens, keeping tech tokens like c++, c#, .net."""
    if not text:
        return []
    return _TOKEN_RE.findall(text.lower())


def keywords(text: str, *, drop_followup_noise: bool = False) -> set[str]:
    """Content-bearing keywords: tokens minus stopwords and very short noise."""
    toks = tokenize(text)
    result = {
        t for t in toks
        if len(t) > 2 and t not in _STOPWORDS
    }
    if drop_followup_noise:
        result = {t for t in result if t not in _FOLLOWUP_NOISE}
    return result


def jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    if inter == 0:
        return 0.0
    return inter / len(a | b)


def overlap_coefficient(a: set[str], b: set[str]) -> float:
    """Overlap relative to the smaller set — better for short prompts vs
    long documents than Jaccard (which is penalised by size disparity)."""
    if not a or not b:
        return 0.0
    inter = len(a & b)
    if inter == 0:
        return 0.0
    return inter / min(len(a), len(b))


def cosine_bow(a: str, b: str) -> float:
    """Cosine similarity over bag-of-words term counts."""
    ca, cb = Counter(tokenize(a)), Counter(tokenize(b))
    if not ca or not cb:
        return 0.0
    shared = set(ca) & set(cb)
    if not shared:
        return 0.0
    dot = sum(ca[t] * cb[t] for t in shared)
    na = math.sqrt(sum(v * v for v in ca.values()))
    nb = math.sqrt(sum(v * v for v in cb.values()))
    return dot / (na * nb) if na and nb else 0.0


class SimilarityScorer:
    """Pluggable similarity backend.

    The default implementation is keyword/lexical based (fast, no deps). A
    future EmbeddingScorer can implement the same two methods and be injected
    into the engine unchanged — this is the seam for semantic vector search.
    """

    def score_texts(self, a: str, b: str) -> float:
        raise NotImplementedError

    def score_keywords(self, a: set[str], b: set[str]) -> float:
        raise NotImplementedError


class LexicalSimilarityScorer(SimilarityScorer):
    def score_texts(self, a: str, b: str) -> float:
        return cosine_bow(a, b)

    def score_keywords(self, a: set[str], b: set[str]) -> float:
        # Blend Jaccard and overlap so short↔long comparisons stay fair.
        return 0.5 * jaccard(a, b) + 0.5 * overlap_coefficient(a, b)
