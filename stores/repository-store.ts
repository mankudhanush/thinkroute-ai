"use client";

import { create } from "zustand";
import {
  scanRepository,
  buildRepositoryIndex,
  sendRepositoryChat,
  generateRepositoryEdit,
  applyRepositoryEdit,
} from "@/services/repository-api";
import { useToastStore } from "@/stores/toast-store";
import type {
  RepositoryStatus,
  RepositoryInfo,
  RepositoryContextState,
  EditPreview,
  ChatMode,
  ChatWorkflowStage,
  EditWorkflowStage,
} from "@/types/repository";
import type { ProviderId } from "@/types/provider";

interface RepositoryStore {
  /** The indexed repository metadata, null when nothing is loaded. */
  repository: RepositoryInfo | null;
  /** Current indexing / lifecycle status. */
  status: RepositoryStatus;
  /** Chat vs Edit mode toggle. */
  chatMode: ChatMode;
  /** Live workflow stage during repository chat streaming. */
  chatStage: ChatWorkflowStage | null;
  /** Live workflow stage during repository edit streaming. */
  editStage: EditWorkflowStage | null;
  /** Context snapshot from the latest retrieval (shown in right panel). */
  context: RepositoryContextState | null;
  /** Pending edit diff waiting for user approval. */
  editPreview: EditPreview | null;
  /** Whether the diff slide-over is open. */
  diffPanelOpen: boolean;
  /** Last error message. */
  error: string | null;
  /** Whether an async operation is running. */
  isProcessing: boolean;

  // ── Actions ──
  uploadRepository: (path: string) => Promise<void>;
  removeRepository: () => void;
  setChatMode: (mode: ChatMode) => void;
  sendRepositoryMessage: (input: {
    conversationId: string;
    query: string;
    mode: "auto" | "manual";
    provider: ProviderId | null;
    model: string | null;
  }) => Promise<{
    answer: string;
    provider: string;
    model: string;
  }>;
  generateEdit: (input: {
    instruction: string;
    provider: ProviderId | null;
    model: string | null;
  }) => Promise<void>;
  approveEdit: () => Promise<void>;
  cancelEdit: () => void;
  setContext: (ctx: RepositoryContextState | null) => void;
  reset: () => void;
}

const INITIAL_STATE = {
  repository: null,
  status: "idle" as RepositoryStatus,
  chatMode: "chat" as ChatMode,
  chatStage: null,
  editStage: null,
  context: null,
  editPreview: null,
  diffPanelOpen: false,
  error: null,
  isProcessing: false,
};

export const useRepositoryStore = create<RepositoryStore>((set, get) => ({
  ...INITIAL_STATE,

  uploadRepository: async (path: string) => {
    set({ status: "scanning", error: null, isProcessing: true });

    try {
      // Stage 1: Scan
      const scanResult = await scanRepository(path);
      set({ status: "parsing" });

      // Stages 2-4 are handled by the build endpoint
      set({ status: "chunking" });

      // Small delay so UI can show the progression
      await new Promise((r) => setTimeout(r, 300));
      set({ status: "embedding" });

      await new Promise((r) => setTimeout(r, 300));
      set({ status: "indexing" });

      // Stage 5: Build full index
      const buildResult = await buildRepositoryIndex(path);

      const repository: RepositoryInfo = {
        id: buildResult.id,
        name: buildResult.name,
        path,
        framework: buildResult.framework ?? scanResult.framework,
        primaryLanguage: buildResult.primaryLanguage ?? scanResult.primaryLanguage,
        totalFiles: scanResult.totalFiles,
        indexedChunks: buildResult.indexedChunks,
        embeddingModel: buildResult.embeddingModel,
        collectionName: buildResult.collectionName,
      };

      set({
        repository,
        status: "ready",
        isProcessing: false,
      });

      useToastStore
        .getState()
        .showToast(`Repository "${repository.name}" indexed successfully`, "success");
    } catch (error) {
      const message = error instanceof Error ? error.message : "Failed to index repository";
      set({ status: "error", error: message, isProcessing: false });
      useToastStore.getState().showToast(message, "error");
    }
  },

  removeRepository: () => {
    set({ ...INITIAL_STATE });
  },

  setChatMode: (mode) => set({ chatMode: mode }),

  sendRepositoryMessage: async (input) => {
    const repo = get().repository;
    if (!repo) throw new Error("No repository loaded");

    set({ chatStage: "retrieving" });

    try {
      // Simulate stage progression
      await new Promise((r) => setTimeout(r, 200));
      set({ chatStage: "building_prompt" });

      await new Promise((r) => setTimeout(r, 200));
      set({ chatStage: "routing" });

      const result = await sendRepositoryChat({
        conversationId: input.conversationId,
        repositoryId: repo.id,
        query: input.query,
        mode: input.mode,
        provider: input.provider,
        model: input.model,
      });

      set({ chatStage: "generating" });

      // Populate context state for the right panel
      const contextState: RepositoryContextState = {
        repositoryName: repo.name,
        retrievedFiles: result.sources?.map((s) => s.relative_path) ?? [],
        retrievedSymbols: result.sources?.map((s) => s.symbol).filter(Boolean) ?? [],
        topSimilarity: result.sources?.length
          ? Math.max(...result.sources.map((s) => s.score))
          : null,
        chunksUsed: result.context?.included_chunks ?? result.retrieval?.chunks_retrieved ?? 0,
        contextTokens: result.context?.used_tokens ?? 0,
        embeddingModel: repo.embeddingModel ?? "unknown",
      };

      set({ context: contextState, chatStage: null });

      return {
        answer: result.answer,
        provider: result.provider,
        model: result.model,
      };
    } catch (error) {
      set({ chatStage: null });
      throw error;
    }
  },

  generateEdit: async (input) => {
    const repo = get().repository;
    if (!repo) throw new Error("No repository loaded");

    set({ editStage: "retrieving", isProcessing: true });

    try {
      await new Promise((r) => setTimeout(r, 200));
      set({ editStage: "generating_patch" });

      const preview = await generateRepositoryEdit({
        repositoryId: repo.id,
        repositoryPath: repo.path,
        instruction: input.instruction,
        provider: input.provider,
        model: input.model,
      });

      set({ editStage: "building_diff" });
      await new Promise((r) => setTimeout(r, 300));

      set({
        editPreview: preview,
        editStage: "awaiting_approval",
        diffPanelOpen: true,
        isProcessing: false,
      });
    } catch (error) {
      const message = error instanceof Error ? error.message : "Failed to generate edit";
      set({ editStage: null, isProcessing: false });
      useToastStore.getState().showToast(message, "error");
    }
  },

  approveEdit: async () => {
    const { editPreview, repository } = get();
    if (!editPreview || !repository) return;

    set({ isProcessing: true });

    try {
      const result = await applyRepositoryEdit({
        repositoryPath: repository.path,
        edits: editPreview.edits,
      });

      set({
        editPreview: null,
        diffPanelOpen: false,
        editStage: null,
        isProcessing: false,
      });

      useToastStore
        .getState()
        .showToast(result.summary || "Changes applied successfully", "success");
    } catch (error) {
      const message = error instanceof Error ? error.message : "Failed to apply changes";
      set({ isProcessing: false });
      useToastStore.getState().showToast(message, "error");
    }
  },

  cancelEdit: () => {
    set({
      editPreview: null,
      diffPanelOpen: false,
      editStage: null,
    });
  },

  setContext: (ctx) => set({ context: ctx }),

  reset: () => set({ ...INITIAL_STATE }),
}));
