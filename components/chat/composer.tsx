"use client";

import { FormEvent, KeyboardEvent } from "react";
import { Database, Paperclip, Pencil, SendHorizontal, Square, Trash2 } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { useTextareaAutosize } from "@/hooks/use-textarea-autosize";
import { useChatStore } from "@/stores/chat-store";
import { useModelStore } from "@/stores/model-store";
import { useRepositoryStore } from "@/stores/repository-store";
import { useSettingsStore } from "@/stores/settings-store";
import { useStreamingStore } from "@/stores/streaming-store";

export function Composer() {
  const draft = useChatStore((state) => state.draft);
  const setDraft = useChatStore((state) => state.setDraft);
  const sendMessage = useChatStore((state) => state.sendMessage);
  const clearConversation = useChatStore((state) => state.clearConversation);
  const isSending = useChatStore((state) => state.isSending);
  const messageCount = useChatStore((state) => state.messages.length);
  const selectedModel = useModelStore((state) => state.selectedModel);
  const routingMode = useSettingsStore((state) => state.routingMode);
  const textareaRef = useTextareaAutosize(draft);

  // Streaming state
  const isStreaming = useStreamingStore((state) => state.isStreaming);
  const stopStreaming = useStreamingStore((state) => state.stop);

  // Repository state
  const repoStatus = useRepositoryStore((s) => s.status);
  const chatMode = useRepositoryStore((s) => s.chatMode);
  const chatStage = useRepositoryStore((s) => s.chatStage);
  const editStage = useRepositoryStore((s) => s.editStage);
  const isRepoProcessing = useRepositoryStore((s) => s.isProcessing);
  const generateEdit = useRepositoryStore((s) => s.generateEdit);

  const isAuto = routingMode === "auto";
  const hasRepo = repoStatus === "ready";
  const isEditMode = hasRepo && chatMode === "edit";
  const isBusy = isSending || isStreaming || isRepoProcessing;
  const canSend = draft.trim().length > 0 && !isBusy;

  function getPlaceholder() {
    if (isEditMode) {
      return "Describe the edit you want to make...";
    }
    if (hasRepo) {
      return "Ask about the repository...";
    }
    if (isAuto) {
      return "Just type — ThinkRoute will handle the rest...";
    }
    return selectedModel
      ? "Ask the selected model..."
      : "Select a model to start chatting...";
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (isStreaming) return;

    if (isEditMode) {
      // Edit mode: generate an edit via the repository store
      generateEdit({
        instruction: draft,
        provider: isAuto ? null : (selectedModel?.providerId ?? null),
        model: isAuto ? null : (selectedModel?.id ?? null),
      });
      setDraft("");
      return;
    }

    // Normal or repository chat
    sendMessage({
      content: draft,
      modelId: isAuto ? null : (selectedModel?.id ?? null),
      providerId: isAuto ? null : (selectedModel?.providerId ?? null),
    });
  }

  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      if (canSend) {
        event.currentTarget.form?.requestSubmit();
      }
    }
  }

  function handleStopClick() {
    stopStreaming();
  }

  // Active workflow stage
  const activeStage = isEditMode ? editStage : chatStage;

  return (
    <form
      className="mx-auto w-full max-w-4xl border-t border-border bg-background/95 px-4 py-4"
      onSubmit={handleSubmit}
    >
      {/* Workflow stage badge */}
      {activeStage && (
        <div className="mb-2 flex items-center gap-2">
          <span className="relative flex h-2 w-2">
            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-accent opacity-75" />
            <span className="relative inline-flex h-2 w-2 rounded-full bg-accent" />
          </span>
          <span className="text-[11px] font-medium text-accent capitalize">
            {activeStage.replace(/_/g, " ")}...
          </span>
        </div>
      )}

      <div className="rounded-md border border-border bg-secondary/30 p-2 shadow-sm">
        <Textarea
          aria-label="Message"
          className="border-0 bg-transparent shadow-none focus-visible:ring-0"
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={getPlaceholder()}
          ref={textareaRef}
          rows={1}
          disabled={isSending || isRepoProcessing}
          value={draft}
        />
        <div className="flex items-center justify-between gap-3 px-1 pt-2">
          <div className="flex items-center gap-1">
            <Button
              aria-label="Attach file"
              disabled
              size="icon"
              title="Attachments are UI-only in this phase"
              type="button"
              variant="ghost"
            >
              <Paperclip className="h-4 w-4" />
            </Button>
            <Button
              aria-label="Clear conversation"
              disabled={messageCount === 0}
              onClick={clearConversation}
              size="icon"
              title="Clear conversation"
              type="button"
              variant="ghost"
            >
              <Trash2 className="h-4 w-4" />
            </Button>

            {/* Repository mode indicator */}
            {hasRepo && (
              <Badge variant="muted" className="ml-1 gap-1 text-[10px]">
                <Database className="h-2.5 w-2.5" />
                {isEditMode ? "Edit" : "Chat"}
              </Badge>
            )}
          </div>

          {/* Stop Generation / Send button */}
          {isStreaming ? (
            <Button
              type="button"
              onClick={handleStopClick}
              variant="outline"
              className="gap-2 border-destructive/50 text-destructive hover:bg-destructive/10 hover:text-destructive"
            >
              <Square className="h-3.5 w-3.5 fill-current" />
              Stop Generating
            </Button>
          ) : (
            <Button disabled={!canSend} type="submit">
              {isEditMode ? (
                <>
                  <Pencil className="h-4 w-4" />
                  {isRepoProcessing ? "Generating..." : "Generate Edit"}
                </>
              ) : (
                <>
                  <SendHorizontal className="h-4 w-4" />
                  {isSending ? "Sending" : "Send"}
                </>
              )}
            </Button>
          )}
        </div>
      </div>
    </form>
  );
}

