"use client";

import { useState } from "react";
import {
  Database,
  FolderUp,
  Trash2,
  RefreshCw,
  CheckCircle2,
  Loader2,
  Code2,
  Layers,
  Cpu,
  AlertCircle,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { useRepositoryStore } from "@/stores/repository-store";
import { INDEXING_STAGES } from "@/types/repository";
import type { RepositoryStatus } from "@/types/repository";

/* ───────────────────────────────────────────────
 * Stage progress indicator shown during indexing
 * ─────────────────────────────────────────────── */
function IndexingProgress({ current }: { current: RepositoryStatus }) {
  const currentIndex = INDEXING_STAGES.findIndex((s) => s.key === current);

  return (
    <div className="grid gap-1.5">
      {INDEXING_STAGES.map((stage, index) => {
        const isDone = currentIndex > index;
        const isActive = currentIndex === index;

        return (
          <div
            key={stage.key}
            className="flex items-center gap-2 text-xs"
          >
            {isDone ? (
              <CheckCircle2 className="h-3.5 w-3.5 shrink-0 text-emerald-400" />
            ) : isActive ? (
              <Loader2 className="h-3.5 w-3.5 shrink-0 animate-spin text-accent" />
            ) : (
              <div className="h-3.5 w-3.5 shrink-0 rounded-full border border-border" />
            )}
            <span
              className={
                isDone
                  ? "text-muted-foreground line-through"
                  : isActive
                    ? "font-medium text-foreground"
                    : "text-muted-foreground/50"
              }
            >
              {stage.label}
            </span>
          </div>
        );
      })}
    </div>
  );
}

/* ───────────────────────────────────────────────
 * Repository Workspace — left sidebar card
 * ─────────────────────────────────────────────── */
export function RepositoryWorkspace() {
  const status = useRepositoryStore((s) => s.status);
  const repository = useRepositoryStore((s) => s.repository);
  const error = useRepositoryStore((s) => s.error);
  const isProcessing = useRepositoryStore((s) => s.isProcessing);
  const uploadRepository = useRepositoryStore((s) => s.uploadRepository);
  const removeRepository = useRepositoryStore((s) => s.removeRepository);

  const [pathInput, setPathInput] = useState("");
  const [showUpload, setShowUpload] = useState(false);

  const isIndexing =
    status === "scanning" ||
    status === "parsing" ||
    status === "chunking" ||
    status === "embedding" ||
    status === "indexing";

  const isReady = status === "ready";

  function handleUpload() {
    const trimmed = pathInput.trim();
    if (!trimmed) return;
    uploadRepository(trimmed);
    setShowUpload(false);
    setPathInput("");
  }

  function handleChange() {
    setShowUpload(true);
  }

  function handleRemove() {
    removeRepository();
    setPathInput("");
    setShowUpload(false);
  }

  return (
    <div className="space-y-2">
      <p className="text-xs font-medium uppercase tracking-[0.12em] text-muted-foreground">
        Repository
      </p>

      {/* ── Idle state: no repository loaded ── */}
      {status === "idle" && !showUpload && (
        <div className="rounded-md border border-border bg-secondary/15 px-3 py-3">
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <Database className="h-4 w-4 text-accent/60" />
            <span>No repository loaded</span>
          </div>
          <Button
            className="mt-3 w-full gap-2"
            onClick={() => setShowUpload(true)}
            size="sm"
            variant="outline"
          >
            <FolderUp className="h-3.5 w-3.5" />
            Upload Repository
          </Button>
        </div>
      )}

      {/* ── Upload form ── */}
      {(showUpload || status === "idle") && showUpload && (
        <div className="rounded-md border border-accent/25 bg-accent/5 px-3 py-3 space-y-3">
          <label className="block text-xs font-medium text-foreground">
            Repository Path
          </label>
          <input
            type="text"
            value={pathInput}
            onChange={(e) => setPathInput(e.target.value)}
            placeholder="C:\Users\...\my-project"
            className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground/50 focus:border-accent focus:outline-none focus:ring-1 focus:ring-accent/30"
            onKeyDown={(e) => {
              if (e.key === "Enter") handleUpload();
            }}
          />
          <div className="flex gap-2">
            <Button
              className="flex-1 gap-2"
              disabled={!pathInput.trim()}
              onClick={handleUpload}
              size="sm"
            >
              <FolderUp className="h-3.5 w-3.5" />
              Index
            </Button>
            <Button
              onClick={() => {
                setShowUpload(false);
                setPathInput("");
              }}
              size="sm"
              variant="ghost"
            >
              Cancel
            </Button>
          </div>
        </div>
      )}

      {/* ── Indexing progress ── */}
      {isIndexing && (
        <div className="rounded-md border border-accent/25 bg-accent/5 px-3 py-3 space-y-3">
          <div className="flex items-center gap-2 text-sm font-medium text-foreground">
            <Loader2 className="h-4 w-4 animate-spin text-accent" />
            Indexing Repository...
          </div>
          <IndexingProgress current={status} />
        </div>
      )}

      {/* ── Error state ── */}
      {status === "error" && (
        <div className="rounded-md border border-destructive/30 bg-destructive/5 px-3 py-3 space-y-2">
          <div className="flex items-center gap-2 text-sm font-medium text-destructive">
            <AlertCircle className="h-4 w-4" />
            Indexing Failed
          </div>
          {error && (
            <p className="text-xs text-muted-foreground">{error}</p>
          )}
          <Button
            className="w-full gap-2"
            onClick={() => setShowUpload(true)}
            size="sm"
            variant="outline"
          >
            <RefreshCw className="h-3.5 w-3.5" />
            Try Again
          </Button>
        </div>
      )}

      {/* ── Ready state: repository loaded ── */}
      {isReady && repository && (
        <div className="rounded-md border border-border bg-secondary/15 px-3 py-3 space-y-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2 text-sm font-medium text-foreground">
              <Database className="h-4 w-4 text-accent" />
              {repository.name}
            </div>
            <Badge variant="accent">Ready</Badge>
          </div>

          <div className="grid gap-1.5">
            {repository.framework && (
              <div className="flex items-center justify-between text-xs">
                <span className="flex items-center gap-1.5 text-muted-foreground">
                  <Code2 className="h-3 w-3" />
                  Framework
                </span>
                <span className="font-medium text-foreground capitalize">
                  {repository.framework}
                </span>
              </div>
            )}
            {repository.indexedChunks != null && (
              <div className="flex items-center justify-between text-xs">
                <span className="flex items-center gap-1.5 text-muted-foreground">
                  <Layers className="h-3 w-3" />
                  Indexed Chunks
                </span>
                <span className="font-medium text-foreground">
                  {repository.indexedChunks.toLocaleString()}
                </span>
              </div>
            )}
            {repository.embeddingModel && (
              <div className="flex items-center justify-between text-xs">
                <span className="flex items-center gap-1.5 text-muted-foreground">
                  <Cpu className="h-3 w-3" />
                  Embedding Model
                </span>
                <span className="max-w-[120px] truncate font-medium text-foreground text-right">
                  {repository.embeddingModel}
                </span>
              </div>
            )}
          </div>

          <Separator />

          <div className="flex gap-2">
            <Button
              className="flex-1 gap-1.5"
              onClick={handleChange}
              size="sm"
              variant="outline"
              disabled={isProcessing}
            >
              <RefreshCw className="h-3 w-3" />
              Change
            </Button>
            <Button
              className="flex-1 gap-1.5"
              onClick={handleRemove}
              size="sm"
              variant="ghost"
              disabled={isProcessing}
            >
              <Trash2 className="h-3 w-3" />
              Remove
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
