"use client";

import { formatTokenEstimate } from "@/lib/utils";
import type { InferenceMetric } from "@/types/inference";
import type { ModelOption, Provider } from "@/types/provider";

export function useInferenceMetrics(
  provider: Provider | undefined,
  model: ModelOption | null,
  messageCount: number,
): InferenceMetric[] {
  const estimatedTokens = Math.max(128, messageCount * 420);

  return [
    {
      label: "Selected Provider",
      value: provider?.name ?? "Unselected",
      tone: "accent",
    },
    {
      label: "Selected Model",
      value: model?.name ?? "Unselected",
      tone: "accent",
    },
    {
      label: "Routing Mode",
      value: "Manual",
    },
    {
      label: "Context Window",
      value: model?.contextWindow ? formatTokenEstimate(model.contextWindow) : "Unavailable",
    },
    {
      label: "Model Owner",
      value: model?.ownedBy ?? "Provider managed",
    },
    {
      label: "Estimated Tokens",
      value: formatTokenEstimate(estimatedTokens),
    },
    {
      label: "Conversation Memory",
      value: messageCount > 0 ? `${messageCount} stored turns` : "Empty",
    },
  ];
}
