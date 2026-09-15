import type { ChatMessage, ContextInfo } from "@/types/chat";
import type { AutoRoutingResult } from "@/types/inference";
import type {
  ModelOption,
  Provider,
  ProviderId,
} from "@/types/provider";

interface ApiErrorPayload {
  error?: string;
  detail?: string;
}

interface ApiModel {
  id: string;
  name: string;
  provider: ProviderId;
  context_window: number | null;
  owned_by: string | null;
}

interface ApiProvider {
  provider: ProviderId;
  name: string;
  connected: boolean;
  available_models: ApiModel[];
  connected_at: string | null;
}

interface ApiHistoryMessage {
  role: ChatMessage["role"];
  content: string;
  provider: ProviderId;
  model: string;
  created_at: string;
}

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
    public readonly code?: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

function apiBaseUrl() {
  const url = process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "");

  if (!url) {
    throw new ApiError("Backend URL is not configured", 0, "backend_unavailable");
  }

  return url;
}

function modelFromApi(model: ApiModel): ModelOption {
  return {
    id: model.id,
    name: model.name,
    providerId: model.provider,
    contextWindow: model.context_window,
    ownedBy: model.owned_by,
  };
}

function providerFromApi(provider: ApiProvider): Provider {
  return {
    id: provider.provider,
    name: provider.name,
    connected: provider.connected,
    availableModels: provider.available_models.map(modelFromApi),
    connectedAt: provider.connected_at,
  };
}

function apiMessage(payload: ApiErrorPayload, status: number) {
  const messages: Record<string, string> = {
    invalid_api_key: "Invalid API Key",
    missing_api_key: "An API key is required for this provider",
    provider_offline: "Provider Offline",
    provider_timeout: "Provider request timed out",
    no_model_selected: "Select a model before sending a message",
    model_not_found: "The selected model is not available for this provider",
    not_found: "The model or endpoint was not found — the model may be unavailable",
    missing_account_id: "A Cloudflare Account ID is required",
    unsupported_provider: "This provider is not supported",
    provider_request_failed: "The provider rejected the request",
    rate_limited: "Rate limit exceeded — please wait and try again",
  };

  return messages[payload.error ?? ""] ?? payload.detail ?? `Request failed (${status})`;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;

  try {
    response = await fetch(`${apiBaseUrl()}${path}`, {
      ...init,
      headers: {
        "Content-Type": "application/json",
        ...init?.headers,
      },
    });
  } catch {
    throw new ApiError("Backend Unavailable. Check your connection and try again.", 0, "backend_unavailable");
  }

  const payload = (await response.json().catch(() => ({}))) as T & ApiErrorPayload;

  if (!response.ok) {
    throw new ApiError(apiMessage(payload, response.status), response.status, payload.error);
  }

  return payload;
}

export async function getProviders(): Promise<Provider[]> {
  const providers = await request<ApiProvider[]>("/providers");
  return providers.map(providerFromApi);
}

export async function connectProvider(input: {
  provider: ProviderId;
  apiKey?: string;
  baseUrl?: string;
}): Promise<void> {
  await request("/providers/connect", {
    method: "POST",
    body: JSON.stringify({
      provider: input.provider,
      api_key: input.apiKey || undefined,
      optional_base_url: input.baseUrl || undefined,
    }),
  });
}

export async function refreshProviderModels(providerId: string): Promise<ModelOption[]> {
  const models = await request<ApiModel[]>(`/providers/${providerId}/refresh_models`, {
    method: "POST",
  });
  return models.map(modelFromApi);
}

export async function selectBackendModel(
  provider: ProviderId,
  model: string,
): Promise<void> {
  await request("/models/select", {
    method: "POST",
    body: JSON.stringify({ provider, model }),
  });
}

export async function getCurrentModel(): Promise<{
  provider: ProviderId;
  model: string;
}> {
  return request("/models/current");
}

export async function sendChatMessage(input: {
  conversationId: string;
  provider: ProviderId;
  model: string;
  message: string;
}): Promise<{ response: string; createdAt: string; context?: ContextInfo }> {
  const result = await request<{ response: string; created_at: string; context?: ContextInfo }>("/chat", {
    method: "POST",
    body: JSON.stringify({
      conversation_id: input.conversationId,
      provider: input.provider,
      model: input.model,
      message: input.message,
    }),
  });

  return { response: result.response, createdAt: result.created_at, context: result.context ?? undefined };
}

export async function getChatHistory(conversationId: string): Promise<ChatMessage[]> {
  const history = await request<ApiHistoryMessage[]>(
    `/chat/history/${encodeURIComponent(conversationId)}`,
  );

  return history.map((message, index) => ({
    id: `${message.created_at}-${index}`,
    role: message.role,
    content: message.content,
    createdAt: message.created_at,
    providerId: message.provider,
    modelId: message.model,
    status: "complete",
  }));
}

export async function sendAutoChat(input: {
  conversationId: string;
  message: string;
}): Promise<{
  response: string;
  createdAt: string;
  provider: ProviderId;
  model: string;
  routing: AutoRoutingResult;
  context?: ContextInfo;
}> {
  const result = await request<{
    response: string;
    created_at: string;
    provider: ProviderId;
    model: string;
    routing: {
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
    };
    context?: ContextInfo;
  }>("/chat/auto", {
    method: "POST",
    body: JSON.stringify({
      conversation_id: input.conversationId,
      message: input.message,
    }),
  });

  return {
    response: result.response,
    createdAt: result.created_at,
    provider: result.provider,
    model: result.model,
    routing: {
      intent: result.routing.intent,
      complexity: result.routing.complexity,
      confidence: result.routing.confidence,
      estimated_output: result.routing.estimated_output,
      requires_reasoning: result.routing.requires_reasoning,
      requires_code: result.routing.requires_code,
      requires_long_context: result.routing.requires_long_context,
      offline_possible: result.routing.offline_possible,
      reason: result.routing.reason,
      classified_by: result.routing.classified_by,
      classification_ms: result.routing.classification_ms,
      routing_ms: result.routing.routing_ms,
      provider_ms: result.routing.provider_ms,
      total_ms: result.routing.total_ms,
      provider: result.provider,
      model: result.model,
    },
    context: result.context ?? undefined,
  };
}
