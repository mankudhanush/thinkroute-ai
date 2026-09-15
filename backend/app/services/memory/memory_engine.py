from __future__ import annotations

import logging
import time
from dataclasses import dataclass

from app.services.memory import similarity
from app.services.memory.context_analyzer import ContextAnalyzer
from app.services.memory.context_cache import LRUCache
from app.services.memory.context_packet_builder import ContextPacket, ContextPacketBuilder
from app.services.memory.memory_retriever import MemoryRetriever
from app.services.memory.thread_manager import ThreadManager, ThreadView

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class MemoryConfig:
    top_n: int = 5
    # Low floor: thread membership is the primary relevance filter, the
    # threshold just drops literal zero-signal turns. Configurable per spec.
    threshold: float = 3.0
    # Default to sending only the relevant prior USER requests (lean tokens,
    # matches the platform's token-efficiency goal). Flip on to include the
    # assistant replies for richer continuity.
    include_responses: bool = False


class MemoryEngine:
    """Context-Aware Memory Engine facade.

        prompt + full history → analyze → thread → retrieve → context packet

    Provider-independent: the returned packet's turns are handed to whichever
    provider Auto/Manual mode selected. The full history is never sent.
    """

    def __init__(
        self,
        config: MemoryConfig | None = None,
        scorer: similarity.SimilarityScorer | None = None,
    ) -> None:
        self.config = config or MemoryConfig()
        self.scorer = scorer or similarity.LexicalSimilarityScorer()
        self.analyzer = ContextAnalyzer()
        self.threads = ThreadManager(self.analyzer, self.scorer)
        self.retriever = MemoryRetriever(self.scorer)
        self.builder = ContextPacketBuilder()
        # Reconstruction is memoised per (conversation, history-length) so
        # steady-state turns skip the replay entirely.
        self._thread_cache: LRUCache[tuple[str, int], ThreadView] = LRUCache(128)

    def build_context(
        self,
        conversation_id: str,
        prompt: str,
        history: list[dict],
        *,
        top_n: int | None = None,
    ) -> tuple[ContextPacket, float]:
        start = time.perf_counter()

        # Empty history → nothing to retrieve, brand-new thread.
        if not history:
            packet = self.builder.build(
                current_prompt=prompt,
                selected=[],
                thread_id="t1",
                is_new_topic=True,
                total_history=0,
                topic_keywords=self.analyzer.analyze(prompt).topic_keywords,
            )
            return packet, (time.perf_counter() - start) * 1000

        analysis = self.analyzer.analyze(prompt)

        cache_key = (conversation_id, len(history))
        view = self._thread_cache.get(cache_key)
        if view is None:
            view = self.threads.reconstruct(history)
            self._thread_cache.put(cache_key, view)

        thread_id, is_new, _domain = self.threads.assign(view, prompt, analysis)
        target = view.by_id.get(thread_id)

        selected = []
        if target is not None and not is_new:
            selected = self.retriever.retrieve(
                history,
                target,
                analysis,
                top_n=top_n or self.config.top_n,
                threshold=self.config.threshold,
                include_responses=self.config.include_responses,
            )

        packet = self.builder.build(
            current_prompt=prompt,
            selected=selected,
            thread_id=thread_id,
            is_new_topic=is_new,
            total_history=sum(1 for m in history if m.get("role") == "user"),
            topic_keywords=analysis.topic_keywords,
        )

        elapsed_ms = (time.perf_counter() - start) * 1000
        logger.info(
            "[MemoryEngine] thread=%s new=%s | used %d/%d msgs | %.2fms",
            thread_id, is_new, packet.used_count, packet.total_history, elapsed_ms,
        )
        return packet, elapsed_ms

    @staticmethod
    def to_context_info(packet: ContextPacket, engine_ms: float):
        """Map a packet to the API ContextInfo model (imported lazily to keep
        the memory package free of schema dependencies)."""
        from app.models.schemas import ContextInfo, ContextMessageInfo

        return ContextInfo(
            used=packet.used_count > 0,
            thread_id=packet.thread_id,
            is_new_topic=packet.is_new_topic,
            used_count=packet.used_count,
            total_history=packet.total_history,
            reason=packet.reason,
            messages=[
                ContextMessageInfo(role=m.role, content=m.content, score=m.score)
                for m in packet.context
            ],
            topic_keywords=packet.topic_keywords,
            engine_ms=round(engine_ms, 2),
        )

    def keywords_csv(self, text: str) -> str:
        return ",".join(sorted(self.analyzer.analyze(text).topic_keywords))

    def invalidate(self, conversation_id: str | None = None) -> None:
        # History length is part of the key, so stale views age out naturally;
        # this is a hard reset hook (e.g. conversation deleted).
        self._thread_cache.clear()
