export type MessageRole = "user" | "assistant" | "system";

export type MessageStatus = "local" | "pending" | "streaming" | "complete" | "error";

export interface ContextMessageInfo {
  role: string;
  content: string;
  score: number;
}

export interface ContextInfo {
  used: boolean;
  thread_id: string;
  is_new_topic: boolean;
  used_count: number;
  total_history: number;
  reason: string;
  messages: ContextMessageInfo[];
  topic_keywords: string[];
  engine_ms: number;
}

export interface ChatMessage {
  id: string;
  role: MessageRole;
  content: string;
  createdAt: string;
  modelId?: string;
  providerId?: string;
  status: MessageStatus;
  routing?: import("@/types/inference").AutoRoutingResult;
  context?: ContextInfo;
}

export interface SendMessageInput {
  content: string;
  modelId: string | null;
  providerId: import("@/types/provider").ProviderId | null;
}
