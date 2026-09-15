"use client";

import { create } from "zustand";
import { getChatHistory, sendAutoChat, sendChatMessage } from "@/services/api-client";
import { createInferenceRequest } from "@/services/inference-service";
import { useRepositoryStore } from "@/stores/repository-store";
import { useSettingsStore } from "@/stores/settings-store";
import { useToastStore } from "@/stores/toast-store";
import type { ChatMessage, SendMessageInput } from "@/types/chat";
import type { AutoRoutingResult, InferenceRequest } from "@/types/inference";

interface ChatStore {
  messages: ChatMessage[];
  draft: string;
  conversationId: string | null;
  latestRequest: InferenceRequest | null;
  latestRouting: AutoRoutingResult | null;
  isSending: boolean;
  isLoadingHistory: boolean;
  setDraft: (draft: string) => void;
  sendMessage: (input: SendMessageInput) => Promise<void>;
  loadConversation: (conversationId: string) => Promise<void>;
  clearConversation: () => void;
}

export const useChatStore = create<ChatStore>((set, get) => ({
  messages: [],
  draft: "",
  conversationId: null,
  latestRequest: null,
  latestRouting: null,
  isSending: false,
  isLoadingHistory: false,
  setDraft: (draft) => set({ draft }),
  sendMessage: async ({ content, modelId, providerId }) => {
    const trimmed = content.trim();

    if (!trimmed) {
      return;
    }

    const routingMode = useSettingsStore.getState().routingMode;

    // In manual mode, require provider and model (unless repository is handling it)
    const repoStore = useRepositoryStore.getState();
    const hasRepo = repoStore.status === "ready" && repoStore.chatMode === "chat";

    if (routingMode === "manual" && !hasRepo) {
      if (!providerId || !modelId) {
        useToastStore.getState().showToast("Select a provider and model before sending a message", "error");
        return;
      }
    }

    const conversationId = get().conversationId ?? crypto.randomUUID();

    const message: ChatMessage = {
      id: crypto.randomUUID(),
      role: "user",
      content: trimmed,
      createdAt: new Date().toISOString(),
      modelId: modelId ?? undefined,
      providerId: providerId ?? undefined,
      status: "pending",
    };

    set({
      messages: [...get().messages, message],
      draft: "",
      conversationId,
      isSending: true,
    });

    try {
      // ── Repository chat branch ──
      if (hasRepo) {
        const result = await repoStore.sendRepositoryMessage({
          conversationId,
          query: trimmed,
          mode: routingMode,
          provider: providerId,
          model: modelId,
        });

        const latestRequest = createInferenceRequest({
          routingMode,
          providerId: result.provider,
          modelId: result.model,
          messageId: message.id,
        });

        set((state) => {
          const assistantMessage: ChatMessage = {
            id: crypto.randomUUID(),
            role: "assistant",
            content: result.answer,
            createdAt: new Date().toISOString(),
            modelId: result.model,
            providerId: result.provider,
            status: "complete",
          };

          return {
            isSending: false,
            latestRequest,
            messages: [
              ...state.messages.map((item): ChatMessage =>
                item.id === message.id ? { ...item, status: "complete", providerId: result.provider, modelId: result.model } : item,
              ),
              assistantMessage,
            ],
          };
        });

        return;
      }

      // ── Auto mode: existing flow ──
      if (routingMode === "auto") {
        const result = await sendAutoChat({
          conversationId,
          message: trimmed,
        });

        const latestRequest = createInferenceRequest({
          routingMode: "auto",
          providerId: result.provider,
          modelId: result.model,
          messageId: message.id,
        });

        set((state) => {
          const assistantMessage: ChatMessage = {
            id: crypto.randomUUID(),
            role: "assistant",
            content: result.response,
            createdAt: result.createdAt,
            modelId: result.model,
            providerId: result.provider,
            status: "complete",
            routing: result.routing,
            context: result.context,
          };

          return {
            isSending: false,
            latestRequest,
            latestRouting: result.routing,
            messages: [
              ...state.messages.map((item): ChatMessage =>
                item.id === message.id ? { ...item, status: "complete", providerId: result.provider, modelId: result.model } : item,
              ),
              assistantMessage,
            ],
          };
        });
      } else {
        // ── Manual mode: existing flow ──
        const latestRequest = createInferenceRequest({
          routingMode: "manual",
          providerId: providerId!,
          modelId: modelId!,
          messageId: message.id,
        });

        set({ latestRequest, latestRouting: null });

        const result = await sendChatMessage({
          conversationId,
          provider: providerId!,
          model: modelId!,
          message: trimmed,
        });

        set((state) => {
          const assistantMessage: ChatMessage = {
            id: crypto.randomUUID(),
            role: "assistant",
            content: result.response,
            createdAt: result.createdAt,
            modelId: modelId!,
            providerId: providerId!,
            status: "complete",
            context: result.context,
          };

          return {
            isSending: false,
            messages: [
              ...state.messages.map((item): ChatMessage =>
                item.id === message.id ? { ...item, status: "complete" } : item,
              ),
              assistantMessage,
            ],
          };
        });
      }
    } catch (error) {
      const messageText = error instanceof Error ? error.message : "Unable to send message";
      set((state) => ({
        isSending: false,
        messages: state.messages.map((item): ChatMessage =>
          item.id === message.id ? { ...item, status: "error" } : item,
        ),
      }));
      useToastStore.getState().showToast(messageText, "error");
    }
  },
  loadConversation: async (conversationId) => {
    set({ isLoadingHistory: true });
    try {
      const messages = await getChatHistory(conversationId);
      set({ messages, conversationId, latestRequest: null, latestRouting: null });
    } catch (error) {
      const message = error instanceof Error ? error.message : "Unable to load conversation";
      useToastStore.getState().showToast(message, "error");
    } finally {
      set({ isLoadingHistory: false });
    }
  },
  clearConversation: () =>
    set({
      messages: [],
      conversationId: null,
      latestRequest: null,
      latestRouting: null,
      draft: "",
    }),
}));

