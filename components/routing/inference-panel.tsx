"use client";

import { Activity, Clock3, Cpu, Route, Sparkles, Zap } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { RepositoryContextPanel } from "@/components/routing/repository-context-panel";
import { useInferenceMetrics } from "@/hooks/use-inference-metrics";
import { formatRelativeTime } from "@/lib/utils";
import { useChatStore } from "@/stores/chat-store";
import { useModelStore } from "@/stores/model-store";
import { useProviderStore } from "@/stores/provider-store";
import { useSettingsStore } from "@/stores/settings-store";

const PROVIDER_LABELS: Record<string, string> = {
  gemini: "Google Gemini",
  groq: "Groq",
  cloudflare: "Cloudflare Workers AI",
  ollama: "Ollama",
};

export function InferencePanel() {
  const selectedProviderId = useProviderStore((state) => state.selectedProviderId);
  const provider = useProviderStore((state) => state.providers.find((item) => item.id === selectedProviderId));
  const selectedModel = useModelStore((state) => state.selectedModel);
  const messageCount = useChatStore((state) => state.messages.length);
  const latestRequest = useChatStore((state) => state.latestRequest);
  const latestRouting = useChatStore((state) => state.latestRouting);
  const isSending = useChatStore((state) => state.isSending);
  const routingMode = useSettingsStore((state) => state.routingMode);
  const isAuto = routingMode === "auto";
  const metrics = useInferenceMetrics(
    provider,
    selectedModel,
    messageCount,
  );

  return (
    <aside className="flex h-full min-h-[720px] flex-col px-4 py-4 lg:min-h-0">
      <header className="flex h-14 items-center gap-3">
        <div className="flex h-9 w-9 items-center justify-center rounded-md border border-border bg-secondary">
          <Route className="h-4 w-4" />
        </div>
        <div className="min-w-0">
          <h2 className="truncate text-sm font-semibold">Inference</h2>
          <p className="truncate text-xs text-muted-foreground">
            {isAuto
              ? "Auto-routed"
              : `${provider?.name ?? "N/A"} / ${selectedModel?.name ?? "Unselected"}`}
          </p>
        </div>
      </header>
      <Separator className="my-3" />
      <div className="flex-1 space-y-6 overflow-y-auto pb-2 pr-1">
        <section className="space-y-2">
          <div className="flex items-center justify-between">
            <p className="text-xs font-medium uppercase tracking-[0.12em] text-muted-foreground">
              Request State
            </p>
            <Activity className="h-3.5 w-3.5 text-muted-foreground" />
          </div>
          <div className="rounded-md border border-border bg-secondary/30 px-3 py-3">
            <div className="flex items-center justify-between gap-3">
              <span className="text-sm font-medium">
                {isSending ? "Routing..." : latestRequest ? "Completed" : "Waiting"}
              </span>
              <Badge variant={isSending || latestRequest ? "accent" : "muted"}>
                {isAuto ? "Auto" : "Manual"}
              </Badge>
            </div>
            <p className="mt-2 text-xs leading-5 text-muted-foreground">
              {isSending
                ? isAuto
                  ? "Classifying intent → selecting provider → generating response..."
                  : "The selected provider is processing the current request."
                : latestRequest
                  ? isAuto
                    ? "The latest request was automatically classified and routed."
                    : "The latest request was sent through the selected provider."
                  : isAuto
                    ? "Type a message and ThinkRoute will handle the routing."
                    : "Select a connected provider and model to begin."}
            </p>
          </div>
        </section>

        {/* Auto Mode: Full Routing Details */}
        {isAuto && latestRouting ? (
          <section className="space-y-2">
            <div className="flex items-center justify-between">
              <p className="text-xs font-medium uppercase tracking-[0.12em] text-muted-foreground">
                Auto Routing
              </p>
              <Sparkles className="h-3.5 w-3.5 text-muted-foreground" />
            </div>
            <div className="grid gap-2">
              {[
                { label: "Intent", value: latestRouting.intent.replace("_", " ") },
                { label: "Complexity", value: latestRouting.complexity },
                { label: "Provider", value: PROVIDER_LABELS[latestRouting.provider] ?? latestRouting.provider },
                { label: "Model", value: latestRouting.model },
                { label: "Confidence", value: `${Math.round(latestRouting.confidence * 100)}%` },
                { label: "Classifier", value: latestRouting.classified_by === "model" ? "Intent model" : latestRouting.classified_by === "fallback" ? "Fallback" : "Fast rules" },
                { label: "Response Time", value: `${(latestRouting.total_ms / 1000).toFixed(2)} s` },
              ].map((item) => (
                <div
                  className="flex min-h-11 items-center justify-between gap-3 rounded-md border border-border bg-secondary/20 px-3 py-2"
                  key={item.label}
                >
                  <span className="min-w-0 truncate text-xs text-muted-foreground">
                    {item.label}
                  </span>
                  <span className="max-w-[180px] truncate text-right text-xs font-medium capitalize text-foreground">
                    {item.value}
                  </span>
                </div>
              ))}
            </div>
            {latestRouting.reason ? (
              <div className="rounded-md border border-border bg-secondary/10 px-3 py-2">
                <p className="text-xs font-medium text-muted-foreground mb-1">Reason</p>
                <p className="text-xs text-foreground leading-5">{latestRouting.reason}</p>
              </div>
            ) : null}
          </section>
        ) : null}

        {/* Manual Mode: Metrics */}
        {!isAuto ? (
          <section className="space-y-2">
            <div className="flex items-center justify-between">
              <p className="text-xs font-medium uppercase tracking-[0.12em] text-muted-foreground">
                Metrics
              </p>
              <Zap className="h-3.5 w-3.5 text-muted-foreground" />
            </div>
            <div className="grid gap-2">
              {metrics.map((metric) => (
                <div
                  className="flex min-h-11 items-center justify-between gap-3 rounded-md border border-border bg-secondary/20 px-3 py-2"
                  key={metric.label}
                >
                  <span className="min-w-0 truncate text-xs text-muted-foreground">
                    {metric.label}
                  </span>
                  <span className="max-w-[150px] truncate text-right text-xs font-medium text-foreground">
                    {metric.value}
                  </span>
                </div>
              ))}
            </div>
          </section>
        ) : null}

        <section className="space-y-2">
          <div className="flex items-center justify-between">
            <p className="text-xs font-medium uppercase tracking-[0.12em] text-muted-foreground">
              Latest Draft
            </p>
            <Clock3 className="h-3.5 w-3.5 text-muted-foreground" />
          </div>
          <div className="rounded-md border border-border bg-secondary/20 px-3 py-3 text-xs text-muted-foreground">
            {latestRequest ? (
              <dl className="grid gap-2">
                <div className="flex justify-between gap-3">
                  <dt>Created</dt>
                  <dd className="text-foreground">
                    {formatRelativeTime(new Date(latestRequest.createdAt))}
                  </dd>
                </div>
                <div className="flex justify-between gap-3">
                  <dt>Mode</dt>
                  <dd className="text-foreground capitalize">{latestRequest.routingMode}</dd>
                </div>
                <div className="flex justify-between gap-3">
                  <dt>Provider</dt>
                  <dd className="text-foreground">
                    {PROVIDER_LABELS[latestRequest.providerId] ?? latestRequest.providerId}
                  </dd>
                </div>
                <div className="flex justify-between gap-3">
                  <dt>Model</dt>
                  <dd className="text-right text-foreground">{latestRequest.modelId}</dd>
                </div>
              </dl>
            ) : (
              <div className="flex items-center gap-2">
                <Cpu className="h-4 w-4 text-accent" />
                No request drafted yet
              </div>
            )}
          </div>
        </section>

        {/* Repository context — only shown when context exists */}
        <RepositoryContextPanel />
      </div>
    </aside>
  );
}
