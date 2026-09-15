import { ApiError } from "@/services/api-client";
import type {
  EditPreview,
  FileEditPayload,
  RepositoryInfo,
} from "@/types/repository";
import type { ProviderId } from "@/types/provider";

/**
 * Thin client for the Repository Intelligence backend endpoints. Kept separate
 * from the core api-client so nothing existing is touched; it mirrors that
 * file's request/error conventions.
 */

interface ApiErrorPayload {
  error?: string;
  detail?: string;
}

function apiBaseUrl() {
  const url = process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "");
  if (!url) {
    throw new ApiError("Backend URL is not configured", 0, "backend_unavailable");
  }
  return url;
}

const REPOSITORY_ERRORS: Record<string, string> = {
  vector_store_unavailable: "Repository index store is unavailable (ChromaDB not installed).",
  embedding_provider_unavailable: "Embedding provider (Ollama) is unavailable.",
  repository_not_indexed: "This repository has not been indexed yet.",
  invalid_repository_path: "That repository path could not be found.",
  empty_repository: "No supported files were found at that path.",
  no_provider_available: "No connected provider is available to answer.",
  approval_required: "Approve the changes before applying.",
  edit_conflict: "A file changed since the diff was generated.",
  edit_missing_file: "A referenced file no longer exists.",
  patch_parse_error: "The model returned an edit plan that could not be parsed.",
};

async function request<T>(path: string, body: unknown): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${apiBaseUrl()}${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  } catch {
    throw new ApiError("Backend unavailable. Check your connection and try again.", 0, "backend_unavailable");
  }

  const payload = (await response.json().catch(() => ({}))) as T & ApiErrorPayload;
  if (!response.ok) {
    const message =
      REPOSITORY_ERRORS[payload.error ?? ""] ?? payload.detail ?? `Request failed (${response.status})`;
    throw new ApiError(message, response.status, payload.error);
  }
  return payload;
}

// ---------------------------------------------------------------------------
// Indexing (scan for metadata, then build the vector index)
// ---------------------------------------------------------------------------

interface ScanResponse {
  repository: { name: string; primary_language: string | null; primary_framework: { name: string } | null };
  statistics: { total_files: number };
  framework: { name: string } | null;
}

export async function scanRepository(
  repositoryPath: string,
): Promise<{ name: string; framework: string | null; primaryLanguage: string | null; totalFiles: number }> {
  const result = await request<ScanResponse>("/repository/index", {
    repository_path: repositoryPath,
    include_files: false,
  });
  return {
    name: result.repository.name,
    framework: result.framework?.name ?? result.repository.primary_framework?.name ?? null,
    primaryLanguage: result.repository.primary_language ?? null,
    totalFiles: result.statistics.total_files,
  };
}

interface BuildResponse {
  repository_id: string;
  repository_name: string;
  root_path: string;
  primary_language: string | null;
  primary_framework: string | null;
  collection_name: string;
  embedding_model: string;
  statistics: { collection_size: number };
}

export async function buildRepositoryIndex(
  repositoryPath: string,
): Promise<Pick<RepositoryInfo, "id" | "name" | "path" | "framework" | "primaryLanguage" | "indexedChunks" | "embeddingModel" | "collectionName">> {
  const result = await request<BuildResponse>("/repository/index/build", {
    repository_path: repositoryPath,
  });
  return {
    id: result.repository_id,
    name: result.repository_name,
    path: result.root_path,
    framework: result.primary_framework,
    primaryLanguage: result.primary_language,
    indexedChunks: result.statistics.collection_size,
    embeddingModel: result.embedding_model,
    collectionName: result.collection_name,
  };
}

// ---------------------------------------------------------------------------
// Chat
// ---------------------------------------------------------------------------

interface ChatApiResponse {
  answer: string;
  provider: string;
  model: string;
  mode: string;
  task: string;
  retrieval: { chunks_retrieved: number; chunks_expanded: number; final_result_count: number };
  context: { window_tokens: number; used_tokens: number; included_chunks: number; trimmed_chunks: number };
  sources: {
    symbol: string;
    chunk_type: string;
    relative_path: string;
    start_line: number;
    end_line: number;
    score: number;
  }[];
  routing: Record<string, unknown> | null;
}

export async function sendRepositoryChat(input: {
  conversationId: string;
  repositoryId: string;
  query: string;
  mode: "auto" | "manual";
  provider: ProviderId | null;
  model: string | null;
}): Promise<ChatApiResponse> {
  return request<ChatApiResponse>("/repository/chat", {
    conversation_id: input.conversationId,
    repository_id: input.repositoryId,
    query: input.query,
    mode: input.mode,
    provider: input.provider ?? undefined,
    model: input.model ?? undefined,
  });
}

// ---------------------------------------------------------------------------
// Editing
// ---------------------------------------------------------------------------

export async function generateRepositoryEdit(input: {
  repositoryId: string;
  repositoryPath: string;
  instruction: string;
  provider: ProviderId | null;
  model: string | null;
}): Promise<EditPreview> {
  return request<EditPreview>("/repository/edit", {
    repository_id: input.repositoryId,
    repository_path: input.repositoryPath,
    instruction: input.instruction,
    provider: input.provider ?? undefined,
    model: input.model ?? undefined,
  });
}

interface ApplyResponse {
  applied: { path: string; action: string; status: string; detail: string }[];
  conflicts: { path: string; action: string; status: string; detail: string }[];
  summary: string;
}

export async function applyRepositoryEdit(input: {
  repositoryPath: string;
  edits: FileEditPayload[];
}): Promise<ApplyResponse> {
  return request<ApplyResponse>("/repository/apply", {
    repository_path: input.repositoryPath,
    edits: input.edits,
    approved: true,
  });
}
