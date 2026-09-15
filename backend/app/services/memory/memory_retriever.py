from __future__ import annotations

from dataclasses import dataclass

from app.services.memory import similarity
from app.services.memory.context_analyzer import PromptAnalysis
from app.services.memory.thread_manager import Thread


@dataclass
class ScoredMessage:
    index: int
    role: str
    content: str
    score: float  # 0..100


# Relevance weighting. Kept explicit so the mix is tunable and auditable.
_W_SIMILARITY = 55.0   # keyword/lexical similarity to the current prompt
_W_KEYWORD = 20.0      # raw keyword overlap
_W_RECENCY = 15.0      # newer turns matter more
_W_ANCHOR = 10.0       # the thread's originating request is core context


class MemoryRetriever:
    """Scores the messages of a thread against the current prompt and returns
    the most relevant ones. Provider-independent, pure Python.
    """

    def __init__(self, scorer: similarity.SimilarityScorer) -> None:
        self.scorer = scorer

    def retrieve(
        self,
        history: list[dict],
        thread: Thread,
        analysis: PromptAnalysis,
        *,
        top_n: int,
        threshold: float,
        include_responses: bool,
    ) -> list[ScoredMessage]:
        if not thread.user_indices:
            return []

        prompt_kw = analysis.topic_keywords or analysis.keywords
        anchor_index = thread.user_indices[0]
        newest = max(thread.user_indices)
        oldest = min(thread.user_indices)
        span = max(1, newest - oldest)

        scored: list[ScoredMessage] = []
        for idx in thread.user_indices:
            msg = history[idx]
            content = msg.get("content") or ""
            msg_kw = similarity.keywords(content, drop_followup_noise=True)

            sim = self.scorer.score_keywords(prompt_kw, msg_kw) if prompt_kw else 0.0
            kw_overlap = similarity.overlap_coefficient(prompt_kw, msg_kw) if prompt_kw else 0.0
            recency = (idx - oldest) / span  # 0 (oldest) .. 1 (newest)
            anchor = 1.0 if idx == anchor_index else 0.0

            raw = (
                _W_SIMILARITY * sim
                + _W_KEYWORD * kw_overlap
                + _W_RECENCY * recency
                + _W_ANCHOR * anchor
            )
            scored.append(ScoredMessage(index=idx, role="user", content=content, score=round(raw, 1)))

        # A bare reference ("continue") has no keywords to match — return the
        # thread's most recent turns by recency, ignoring the score threshold
        # (thread membership is itself the relevance signal here).
        if not prompt_kw:
            scored.sort(key=lambda s: s.index, reverse=True)
            selected = scored[:top_n]
        else:
            scored.sort(key=lambda s: (s.score, s.index), reverse=True)
            selected = [s for s in scored if s.score >= threshold][:top_n]
            # Everything below threshold (e.g. no lexical overlap) — still keep
            # the most relevant turns, since they're all in the chosen thread.
            if not selected:
                selected = scored[: min(top_n, len(scored))]

        if include_responses:
            selected = self._attach_responses(history, selected)

        # Return in chronological order for a natural transcript.
        selected.sort(key=lambda s: s.index)
        return selected

    @staticmethod
    def _attach_responses(history: list[dict], selected: list[ScoredMessage]) -> list[ScoredMessage]:
        """Include each selected user turn's assistant reply so the provider
        sees what was actually produced (real continuity, not just requests)."""
        out: list[ScoredMessage] = []
        chosen = {s.index for s in selected}
        for s in selected:
            out.append(s)
            reply_idx = s.index + 1
            if reply_idx < len(history) and history[reply_idx].get("role") == "assistant" and reply_idx not in chosen:
                out.append(
                    ScoredMessage(
                        index=reply_idx,
                        role="assistant",
                        content=history[reply_idx].get("content") or "",
                        score=s.score,
                    )
                )
        return out
