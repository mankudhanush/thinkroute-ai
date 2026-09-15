"use client";

import { useState } from "react";
import { Cpu, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { useModelStore } from "@/stores/model-store";
import { useProviderStore } from "@/stores/provider-store";
import { useToastStore } from "@/stores/toast-store";
import { refreshProviderModels } from "@/services/api-client";

export function ModelPicker() {
  const selectedModel = useModelStore((state) => state.selectedModel);
  const selectModel = useModelStore((state) => state.selectModel);
  const isSelecting = useModelStore((state) => state.isSelecting);
  const selectedProviderId = useProviderStore((state) => state.selectedProviderId);
  const provider = useProviderStore((state) => state.providers.find((item) => item.id === selectedProviderId));
  const refreshProviders = useProviderStore((state) => state.refreshProviders);
  const showToast = useToastStore((state) => state.showToast);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const models = provider?.availableModels ?? [];

  async function handleModelSelect(model: (typeof models)[number]) {
    try {
      await selectModel(model);
    } catch (error) {
      showToast(error instanceof Error ? error.message : "Unable to select model", "error");
    }
  }

  async function handleRefreshModels() {
    if (!selectedProviderId) return;
    setIsRefreshing(true);
    try {
      await refreshProviderModels(selectedProviderId);
      await refreshProviders();
      showToast("Models successfully validated and refreshed", "success");
    } catch (error) {
      showToast(error instanceof Error ? error.message : "Unable to refresh models", "error");
    } finally {
      setIsRefreshing(false);
    }
  }

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <p className="text-xs font-medium uppercase tracking-[0.12em] text-muted-foreground">
          Manual Model Selection
        </p>
        <div className="flex items-center gap-1">
          {selectedProviderId && provider?.connected ? (
            <Button disabled={isRefreshing} onClick={handleRefreshModels} size="icon" title="Refresh Models" variant="ghost" className="h-6 w-6">
              <RefreshCw className={cn("h-3.5 w-3.5 text-muted-foreground", isRefreshing && "animate-spin")} />
            </Button>
          ) : null}
          <Cpu className="h-3.5 w-3.5 text-muted-foreground" />
        </div>
      </div>
      <div className="grid gap-1.5">
        {selectedProviderId && !provider?.connected ? (
          <p className="px-1 text-xs leading-5 text-muted-foreground">Connect the selected provider to load its models.</p>
        ) : null}
        {!selectedProviderId ? (
          <p className="px-1 text-xs leading-5 text-muted-foreground">Select a provider to view available models.</p>
        ) : null}
        {models.map((model) => {
          const selected = selectedModel?.providerId === model.providerId && selectedModel.id === model.id;

          return (
            <button
              className={cn(
                "flex min-h-14 w-full items-center justify-between rounded-md border px-3 py-2 text-left transition-colors",
                selected
                  ? "border-accent/50 bg-accent/10 text-foreground"
                  : "border-transparent text-muted-foreground hover:border-border hover:bg-secondary/35 hover:text-foreground",
              )}
              disabled={isSelecting}
              key={model.id}
              onClick={() => void handleModelSelect(model)}
              type="button"
            >
              <span className="min-w-0">
                <span className="block truncate text-sm font-medium">
                  {model.name}
                </span>
                <span className="block truncate text-xs text-muted-foreground">
                  {model.ownedBy ?? model.id}
                </span>
              </span>
              <Badge variant={selected ? "accent" : "muted"}>
                {model.contextWindow ? `${model.contextWindow.toLocaleString()} ctx` : "Available"}
              </Badge>
            </button>
          );
        })}
      </div>
    </div>
  );
}
