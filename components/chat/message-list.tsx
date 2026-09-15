"use client";

import { useAutoScroll } from "@/hooks/use-auto-scroll";
import { useChatStore } from "@/stores/chat-store";
import { useRepositoryStore } from "@/stores/repository-store";
import { useStreamingStore } from "@/stores/streaming-store";
import { EmptyState } from "@/components/chat/empty-state";
import { MessageBubble } from "@/components/chat/message-bubble";
import { TypingIndicator } from "@/components/chat/typing-indicator";

const CHAT_STAGE_LABELS: Record<string, string> = {
  retrieving: "Retrieving Repository",
  building_prompt: "Building Context",
  routing: "Routing",
  generating: "Generating Response",
};

const EDIT_STAGE_LABELS: Record<string, string> = {
  retrieving: "Retrieving",
  generating_patch: "Generating Patch",
  building_diff: "Generating Diff",
  awaiting_approval: "Waiting Approval",
};

export function MessageList() {
  const messages = useChatStore((state) => state.messages);
  const isSending = useChatStore((state) => state.isSending);
  const isStreaming = useStreamingStore((state) => state.isStreaming);

  // Repository workflow stage
  const repoStatus = useRepositoryStore((s) => s.status);
  const chatMode = useRepositoryStore((s) => s.chatMode);
  const chatStage = useRepositoryStore((s) => s.chatStage);
  const editStage = useRepositoryStore((s) => s.editStage);
  const isRepoProcessing = useRepositoryStore((s) => s.isProcessing);

  const hasRepo = repoStatus === "ready";
  const activeStage =
    hasRepo && chatMode === "edit" ? editStage : chatStage;
  const stageLabel = activeStage
    ? (chatMode === "edit"
        ? EDIT_STAGE_LABELS[activeStage]
        : CHAT_STAGE_LABELS[activeStage]) ?? null
    : null;

  // Find the latest assistant message id so we can pass isLatestAssistant
  const latestAssistantId = (() => {
    for (let i = messages.length - 1; i >= 0; i--) {
      if (messages[i].role === "assistant") return messages[i].id;
    }
    return null;
  })();

  // Auto-scroll tracks both message count and streaming state
  const scrollRef = useAutoScroll(messages.length, isStreaming);

  if (messages.length === 0) {
    return <EmptyState />;
  }

  return (
    <div className="mx-auto flex w-full max-w-4xl flex-1 flex-col gap-5 px-5 py-6">
      {messages.map((message) => (
        <MessageBubble
          key={message.id}
          message={message}
          isLatestAssistant={message.id === latestAssistantId}
        />
      ))}
      {(isSending || isRepoProcessing) ? (
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          <TypingIndicator />
          {stageLabel ?? "Thinking"}
        </div>
      ) : null}
      <div ref={scrollRef} />
    </div>
  );
}

