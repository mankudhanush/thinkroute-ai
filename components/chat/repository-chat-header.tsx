"use client";

import { Database, MessageSquareCode, Pencil } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { useRepositoryStore } from "@/stores/repository-store";

const CHAT_STAGE_LABELS: Record<string, string> = {
  retrieving: "Retrieving Repository...",
  building_prompt: "Building Context...",
  routing: "Routing...",
  generating: "Generating Response...",
};

const EDIT_STAGE_LABELS: Record<string, string> = {
  retrieving: "Retrieving...",
  generating_patch: "Generating Patch...",
  building_diff: "Generating Diff...",
  awaiting_approval: "Waiting Approval...",
};

export function RepositoryChatHeader() {
  const status = useRepositoryStore((s) => s.status);
  const repository = useRepositoryStore((s) => s.repository);
  const chatMode = useRepositoryStore((s) => s.chatMode);
  const chatStage = useRepositoryStore((s) => s.chatStage);
  const editStage = useRepositoryStore((s) => s.editStage);
  const setChatMode = useRepositoryStore((s) => s.setChatMode);

  if (status !== "ready" || !repository) return null;

  const activeStageLabel =
    chatMode === "chat"
      ? chatStage
        ? CHAT_STAGE_LABELS[chatStage] ?? null
        : null
      : editStage
        ? EDIT_STAGE_LABELS[editStage] ?? null
        : null;

  return (
    <div className="border-b border-border bg-secondary/10 px-5 py-2.5">
      {/* Row 1: Badge + repo info */}
      <div className="flex items-center justify-between gap-3">
        <div className="flex min-w-0 items-center gap-2">
          <span className="flex h-2 w-2 shrink-0 rounded-full bg-emerald-400" />
          <span className="text-xs font-medium text-accent">
            Repository Intelligence
          </span>
          <Separator orientation="vertical" className="mx-1 h-3" />
          <Database className="h-3 w-3 shrink-0 text-muted-foreground" />
          <span className="truncate text-xs text-muted-foreground">
            {repository.name}
          </span>
          {repository.framework && (
            <Badge variant="muted" className="text-[10px]">
              {repository.framework}
            </Badge>
          )}
          {repository.indexedChunks != null && (
            <span className="hidden text-[10px] text-muted-foreground sm:inline">
              {repository.indexedChunks.toLocaleString()} chunks
            </span>
          )}
        </div>

        {/* Chat/Edit toggle */}
        <div className="flex shrink-0 items-center rounded-md border border-border bg-secondary/30 p-0.5">
          <ModeButton
            active={chatMode === "chat"}
            icon={<MessageSquareCode className="h-3 w-3" />}
            label="Chat"
            onClick={() => setChatMode("chat")}
          />
          <ModeButton
            active={chatMode === "edit"}
            icon={<Pencil className="h-3 w-3" />}
            label="Edit"
            onClick={() => setChatMode("edit")}
          />
        </div>
      </div>

      {/* Row 2: Workflow stage (only when active) */}
      {activeStageLabel && (
        <div className="mt-1.5 flex items-center gap-2">
          <span className="relative flex h-2 w-2">
            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-accent opacity-75" />
            <span className="relative inline-flex h-2 w-2 rounded-full bg-accent" />
          </span>
          <span className="text-[11px] font-medium text-accent">
            {activeStageLabel}
          </span>
        </div>
      )}
    </div>
  );
}

/* ── Small toggle button for Chat / Edit ── */
function ModeButton({
  active,
  icon,
  label,
  onClick,
}: {
  active: boolean;
  icon: React.ReactNode;
  label: string;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`flex items-center gap-1.5 rounded px-2.5 py-1 text-[11px] font-medium transition-colors ${
        active
          ? "bg-accent/15 text-accent"
          : "text-muted-foreground hover:text-foreground"
      }`}
    >
      {icon}
      {label}
    </button>
  );
}
