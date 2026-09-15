from __future__ import annotations

from dataclasses import dataclass, field

from app.providers.base_provider import ChatTurn
from app.services.memory.memory_retriever import ScoredMessage


@dataclass
class ContextMessage:
    role: str
    content: str
    score: float


@dataclass
class ContextPacket:
    """The provider-independent bundle sent to whichever model was selected:
    the relevant prior turns plus the current prompt — never the full history.
    """

    current_prompt: str
    context: list[ContextMessage]
    thread_id: str
    is_new_topic: bool
    total_history: int
    used_count: int
    reason: str = ""
    topic_keywords: list[str] = field(default_factory=list)

    def to_chat_turns(self) -> list[ChatTurn]:
        turns = [ChatTurn(m.role, m.content) for m in self.context]
        turns.append(ChatTurn("user", self.current_prompt))
        return turns


class ContextPacketBuilder:
    def build(
        self,
        *,
        current_prompt: str,
        selected: list[ScoredMessage],
        thread_id: str,
        is_new_topic: bool,
        total_history: int,
        topic_keywords: set[str],
    ) -> ContextPacket:
        context = [ContextMessage(role=s.role, content=s.content, score=s.score) for s in selected]

        if not context:
            reason = (
                "New topic — no prior context needed."
                if is_new_topic else "No related earlier messages found."
            )
        else:
            n = len(context)
            reason = f"Reusing {n} relevant message{'s' if n != 1 else ''} from the current thread."

        return ContextPacket(
            current_prompt=current_prompt,
            context=context,
            thread_id=thread_id,
            is_new_topic=is_new_topic,
            total_history=total_history,
            used_count=len(context),
            reason=reason,
            topic_keywords=sorted(topic_keywords),
        )
