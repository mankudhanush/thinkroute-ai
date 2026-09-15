export type ProviderId =
  | "gemini"
  | "groq"
  | "cloudflare"
  | "ollama";

export interface Provider {
  id: ProviderId;
  name: string;
  connected: boolean;
  availableModels: ModelOption[];
  connectedAt: string | null;
}

export interface ModelOption {
  id: string;
  name: string;
  providerId: ProviderId;
  contextWindow: number | null;
  ownedBy: string | null;
}
