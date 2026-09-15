"use client";

import { motion, AnimatePresence } from "framer-motion";
import {
  X,
  FileText,
  CheckCircle2,
  Shield,
  Plus,
  Minus,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useRepositoryStore } from "@/stores/repository-store";
import type { EditFileDiff } from "@/types/repository";

const RISK_COLORS: Record<string, { border: string; bg: string; text: string }> = {
  low: {
    border: "border-emerald-500/30",
    bg: "bg-emerald-500/10",
    text: "text-emerald-400",
  },
  medium: {
    border: "border-amber-500/30",
    bg: "bg-amber-500/10",
    text: "text-amber-400",
  },
  high: {
    border: "border-destructive/30",
    bg: "bg-destructive/10",
    text: "text-destructive",
  },
};

function riskStyle(risk: string) {
  return RISK_COLORS[risk] ?? RISK_COLORS.low;
}

/* ── Single file diff card ── */
function FileDiffCard({ diff }: { diff: EditFileDiff }) {
  const rs = riskStyle(diff.risk);

  return (
    <div className={`rounded-md border ${rs.border} overflow-hidden`}>
      {/* File header */}
      <div className="flex items-center justify-between gap-2 border-b border-border bg-secondary/30 px-3 py-2">
        <div className="flex min-w-0 items-center gap-2">
          <FileText className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
          <span className="truncate text-xs font-medium font-mono text-foreground">
            {diff.path}
          </span>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <span className="flex items-center gap-0.5 text-[10px] text-emerald-400">
            <Plus className="h-2.5 w-2.5" />
            {diff.added_lines}
          </span>
          <span className="flex items-center gap-0.5 text-[10px] text-destructive">
            <Minus className="h-2.5 w-2.5" />
            {diff.removed_lines}
          </span>
          <Badge
            className={`text-[9px] ${rs.bg} ${rs.text} border-transparent`}
          >
            {diff.risk}
          </Badge>
        </div>
      </div>

      {/* Unified diff */}
      <pre className="diff-pre max-h-64 overflow-auto bg-[hsl(240_6%_6%)] px-3 py-2 text-[11px] leading-5 font-mono">
        {diff.unified_diff.split("\n").map((line, i) => {
          let lineClass = "text-muted-foreground";
          if (line.startsWith("+") && !line.startsWith("+++")) {
            lineClass = "text-emerald-400 bg-emerald-500/8";
          } else if (line.startsWith("-") && !line.startsWith("---")) {
            lineClass = "text-destructive bg-destructive/8";
          } else if (line.startsWith("@@")) {
            lineClass = "text-accent/70";
          }

          return (
            <div key={i} className={`${lineClass} px-1 -mx-1 rounded-sm`}>
              {line || " "}
            </div>
          );
        })}
      </pre>
    </div>
  );
}

/* ───────────────────────────────────────────────
 * Diff Panel — slides in from the right
 * ─────────────────────────────────────────────── */
export function DiffPanel() {
  const diffPanelOpen = useRepositoryStore((s) => s.diffPanelOpen);
  const editPreview = useRepositoryStore((s) => s.editPreview);
  const isProcessing = useRepositoryStore((s) => s.isProcessing);
  const approveEdit = useRepositoryStore((s) => s.approveEdit);
  const cancelEdit = useRepositoryStore((s) => s.cancelEdit);

  const overallRisk = editPreview?.overall_risk ?? "low";
  const rs = riskStyle(overallRisk);

  return (
    <AnimatePresence>
      {diffPanelOpen && editPreview && (
        <>
          {/* Backdrop */}
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-40 bg-black/40"
            onClick={cancelEdit}
          />

          {/* Slide-over */}
          <motion.aside
            initial={{ x: "100%" }}
            animate={{ x: 0 }}
            exit={{ x: "100%" }}
            transition={{ type: "spring", damping: 30, stiffness: 300 }}
            className="fixed right-0 top-0 z-50 flex h-dvh w-full max-w-xl flex-col border-l border-border bg-background shadow-2xl"
          >
            {/* ── Header ── */}
            <header className="flex items-center justify-between gap-3 border-b border-border px-5 py-4">
              <div className="min-w-0">
                <h2 className="text-sm font-semibold text-foreground">
                  Edit Preview
                </h2>
                <p className="mt-0.5 truncate text-xs text-muted-foreground">
                  {editPreview.summary}
                </p>
              </div>
              <div className="flex shrink-0 items-center gap-2">
                <Badge className={`${rs.bg} ${rs.text} border-transparent`}>
                  <Shield className="mr-1 h-3 w-3" />
                  {overallRisk} risk
                </Badge>
                <button
                  type="button"
                  onClick={cancelEdit}
                  className="rounded-md p-1.5 text-muted-foreground hover:bg-secondary hover:text-foreground transition-colors"
                >
                  <X className="h-4 w-4" />
                </button>
              </div>
            </header>

            {/* ── Changed files summary ── */}
            <div className="border-b border-border px-5 py-3">
              <p className="text-xs font-medium text-muted-foreground mb-2">
                Changed Files ({editPreview.files_changed.length})
              </p>
              <div className="flex flex-wrap gap-1.5">
                {editPreview.files_changed.map((f) => (
                  <span
                    key={f.path}
                    className="inline-flex items-center gap-1 rounded border border-border bg-secondary/30 px-2 py-0.5 text-[10px] font-mono text-foreground"
                  >
                    <FileText className="h-2.5 w-2.5 text-muted-foreground" />
                    {f.path.split("/").pop() ?? f.path}
                  </span>
                ))}
              </div>
            </div>

            {/* ── Diffs ── */}
            <div className="flex-1 overflow-y-auto px-5 py-4 space-y-4">
              {editPreview.files_changed.map((diff) => (
                <FileDiffCard key={diff.path} diff={diff} />
              ))}
            </div>

            {/* ── Footer actions ── */}
            <footer className="flex items-center justify-between gap-3 border-t border-border px-5 py-4">
              <Button
                onClick={cancelEdit}
                variant="ghost"
                disabled={isProcessing}
              >
                Cancel
              </Button>
              <Button
                className="gap-2"
                onClick={approveEdit}
                disabled={isProcessing}
              >
                {isProcessing ? (
                  <>
                    <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-current border-t-transparent" />
                    Applying...
                  </>
                ) : (
                  <>
                    <CheckCircle2 className="h-4 w-4" />
                    Approve &amp; Apply
                  </>
                )}
              </Button>
            </footer>
          </motion.aside>
        </>
      )}
    </AnimatePresence>
  );
}
