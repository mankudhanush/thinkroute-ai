"use client";

import { create } from "zustand";
import { selectBackendModel } from "@/services/api-client";
import type { ModelOption, ProviderId } from "@/types/provider";

interface ModelStore {
  selectedModel: ModelOption | null;
  isSelecting: boolean;
  selectModel: (model: ModelOption) => Promise<void>;
  setSelectedModel: (model: ModelOption | null) => void;
}

export const useModelStore = create<ModelStore>((set) => ({
  selectedModel: null,
  isSelecting: false,
  selectModel: async (model) => {
    set({ isSelecting: true });
    try {
      await selectBackendModel(model.providerId, model.id);
      set({ selectedModel: model });
    } finally {
      set({ isSelecting: false });
    }
  },
  setSelectedModel: (model) => set({ selectedModel: model }),
}));
