"use client";

import { useEffect, useState } from "react";
import { KeyRound, LoaderCircle, PlugZap } from "lucide-react";
import { ProviderConnectDialog } from "@/components/providers/provider-connect-dialog";
import { cn } from "@/lib/utils";
import { useModelStore } from "@/stores/model-store";
import { useProviderStore } from "@/stores/provider-store";
import { getCurrentModel } from "@/services/api-client";
import { useToastStore } from "@/stores/toast-store";
import type { Provider, ProviderId } from "@/types/provider";

export function ProviderList() {
  const selectedProviderId = useProviderStore((state) => state.selectedProviderId);
  const providers = useProviderStore((state) => state.providers);
  const isLoading = useProviderStore((state) => state.isLoading);
  const refreshProviders = useProviderStore((state) => state.refreshProviders);
  const selectProvider = useProviderStore((state) => state.selectProvider);
  const selectedModel = useModelStore((state) => state.selectedModel);
  const setSelectedModel = useModelStore((state) => state.setSelectedModel);
  const showToast = useToastStore((state) => state.showToast);
  const [providerToConnect, setProviderToConnect] = useState<Provider | null>(null);

  useEffect(() => {
    let active = true;

    async function loadProviders() {
      try {
        const liveProviders = await refreshProviders();
        const current = await getCurrentModel().catch(() => null);

        if (!active || !current) {
          return;
        }

        const provider = liveProviders.find((item) => item.id === current.provider);
        const model = provider?.availableModels.find((item) => item.id === current.model);
        if (provider && model) {
          selectProvider(provider.id);
          setSelectedModel(model);
        }
      } catch (error) {
        if (active) {
          showToast(error instanceof Error ? error.message : "Unable to load providers", "error");
        }
      }
    }

    void loadProviders();
    return () => {
      active = false;
    };
  }, [refreshProviders, selectProvider, setSelectedModel, showToast]);

  function handleProviderSelect(providerId: ProviderId) {
    selectProvider(providerId);
    if (selectedModel?.providerId !== providerId) {
      setSelectedModel(null);
    }
  }

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <p className="text-xs font-medium uppercase tracking-[0.12em] text-muted-foreground">
          Providers
        </p>
        <PlugZap className="h-3.5 w-3.5 text-muted-foreground" />
      </div>
      <div className="grid gap-1.5">
        {isLoading && providers.length === 0 ? (
          <div className="flex min-h-12 items-center gap-2 rounded-md border border-border px-3 text-sm text-muted-foreground">
            <LoaderCircle className="h-4 w-4 animate-spin" />
            Loading providers
          </div>
        ) : null}
        {providers.map((provider) => {
          const selected = selectedProviderId === provider.id;

          return (
            <div
              className={cn(
                "group flex min-h-12 w-full items-center justify-between rounded-md border px-3 py-2 text-left transition-colors",
                selected
                  ? "border-foreground/25 bg-secondary text-foreground"
                  : "border-transparent text-muted-foreground hover:border-border hover:bg-secondary/40 hover:text-foreground",
              )}
              key={provider.id}
            >
              <button
                className="flex min-w-0 flex-1 items-center gap-3 text-left"
                onClick={() => handleProviderSelect(provider.id)}
                type="button"
              >
                <span className={cn("h-2.5 w-2.5 rounded-full", provider.connected ? "bg-emerald-400" : "bg-muted-foreground")} />
                <span className="min-w-0">
                  <span className="block truncate text-sm font-medium">
                    {provider.name}
                  </span>
                  <span
                    className={cn(
                      "mt-0.5 inline-flex rounded-md border px-1.5 py-0.5 text-[10px] font-medium",
                      provider.connected
                        ? "border-emerald-400/35 bg-emerald-400/10 text-emerald-300"
                        : "border-border bg-transparent text-muted-foreground",
                    )}
                  >
                    {provider.connected ? "Connected" : "Disconnected"}
                  </span>
                </span>
              </button>
              <button
                aria-label={`${provider.name} API key`}
                className={cn(
                  "inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-md text-muted-foreground transition-colors group-hover:text-foreground",
                )}
                onClick={() => setProviderToConnect(provider)}
                title={`Connect ${provider.name}`}
                type="button"
              >
                <KeyRound className="h-4 w-4" />
              </button>
            </div>
          );
        })}
      </div>
      <ProviderConnectDialog
        onClose={() => setProviderToConnect(null)}
        onConnected={(provider) => handleProviderSelect(provider.id)}
        provider={providerToConnect}
      />
    </div>
  );
}
