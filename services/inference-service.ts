import type { InferenceRequest, RoutingMode } from "@/types/inference";

interface CreateInferenceDraftInput {
  routingMode: RoutingMode;
  providerId: string;
  modelId: string;
  messageId: string;
}

export function createInferenceRequest(
  input: CreateInferenceDraftInput,
): InferenceRequest {
  return {
    id: crypto.randomUUID(),
    routingMode: input.routingMode,
    providerId: input.providerId,
    modelId: input.modelId,
    messageId: input.messageId,
    createdAt: new Date().toISOString(),
  };
}
