export type RoutingMode = "manual" | "auto";

export interface InferenceRequest {
  id: string;
  routingMode: RoutingMode;
  providerId: string;
  modelId: string;
  messageId: string;
  createdAt: string;
}

export interface InferenceMetric {
  label: string;
  value: string;
  tone?: "default" | "accent" | "muted";
}

export interface AutoRoutingResult {
  intent: string;
  complexity: string;
  confidence: number;
  estimated_output: string;
  requires_reasoning: boolean;
  requires_code: boolean;
  requires_long_context: boolean;
  offline_possible: boolean;
  reason: string;
  classified_by: string;
  classification_ms: number;
  routing_ms: number;
  provider_ms: number;
  total_ms: number;
  provider: string;
  model: string;
}
