"use client";

import { create } from "zustand";
import { connectProvider as connectBackendProvider, getProviders } from "@/services/api-client";
import type { Provider, ProviderId } from "@/types/provider";

interface ProviderStore {
  providers: Provider[];
  selectedProviderId: ProviderId | null;
  isLoading: boolean;
  connectingProviderId: ProviderId | null;
  refreshProviders: () => Promise<Provider[]>;
  connectProvider: (input: { provider: ProviderId; apiKey?: string; baseUrl?: string }) => Promise<void>;
  selectProvider: (providerId: ProviderId) => void;
}

export const useProviderStore = create<ProviderStore>((set) => ({
  providers: [],
  selectedProviderId: null,
  isLoading: false,
  connectingProviderId: null,
  refreshProviders: async () => {
    set({ isLoading: true });
    try {
      const providers = await getProviders();
      set((state) => ({
        providers,
        selectedProviderId:
          state.selectedProviderId && providers.some((provider) => provider.id === state.selectedProviderId)
            ? state.selectedProviderId
            : providers[0]?.id ?? null,
      }));
      return providers;
    } finally {
      set({ isLoading: false });
    }
  },
  connectProvider: async (input) => {
    set({ connectingProviderId: input.provider });
    try {
      await connectBackendProvider(input);
      await useProviderStore.getState().refreshProviders();
    } finally {
      set({ connectingProviderId: null });
    }
  },
  selectProvider: (providerId) => set({ selectedProviderId: providerId }),
}));
