import type { ProviderId } from "@/types/provider";

/** Lifecycle of the workspace repository, drives the staged upload UI. */
export type RepositoryStatus =
  | "idle"
  | "scanning"
  | "parsing"
  | "chunking"
  | "embedding"
  | "indexing"
  | "ready"
  | "error";

/** Ordered indexing stages shown inside the Workspace card. */
export const INDEXING_STAGES: { key: RepositoryStatus; label: string }[] = [
  { key: "scanning", label: "Scanning Repository" },
  { key: "parsing", label: "Parsing Files" },
  { key: "chunking", label: "Generating Chunks" },
  { key: "embedding", label: "Generating Embeddings" },
  { key: "indexing", label: "Building Repository Index" },
  { key: "ready", label: "Repository Ready" },
];

export type ChatMode = "chat" | "edit";

/** Live workflow stages surfaced during repository chat / edit streaming. */
export type ChatWorkflowStage =
  | "retrieving"
  | "building_prompt"
  | "routing"
  | "generating";

export type EditWorkflowStage =
  | "retrieving"
  | "generating_patch"
  | "building_diff"
  | "awaiting_approval";

export interface RepositoryInfo {
  id: string;
  name: string;
  path: string;
  framework: string | null;
  primaryLanguage: string | null;
  totalFiles: number | null;
  indexedChunks: number | null;
  embeddingModel: string | null;
  collectionName: string | null;
}

/** Snapshot of the last retrieval/context, rendered in the right panel. */
export interface RepositoryContextState {
  repositoryName: string;
  retrievedFiles: string[];
  retrievedSymbols: string[];
  topSimilarity: number | null;
  chunksUsed: number;
  contextTokens: number;
  embeddingModel: string;
}

export interface EditFileDiff {
  path: string;
  action: string;
  target_path?: string | null;
  before: string;
  after: string;
  unified_diff: string;
  added_lines: number;
  removed_lines: number;
  risk: "low" | "medium" | "high" | string;
}

/** Opaque structured edit passed straight back to /repository/apply. */
export interface FileEditPayload {
  action: string;
  path: string;
  target_path?: string | null;
  new_content?: string | null;
  expected_before_hash?: string | null;
}

export interface EditPreview {
  repository_id: string;
  repository_name: string;
  instruction: string;
  summary: string;
  provider: string;
  model: string;
  files_changed: EditFileDiff[];
  patch: string;
  edits: FileEditPayload[];
  overall_risk: "low" | "medium" | "high" | string;
}

export interface RepositoryChatOptions {
  mode: "auto" | "manual";
  provider: ProviderId | null;
  model: string | null;
}
