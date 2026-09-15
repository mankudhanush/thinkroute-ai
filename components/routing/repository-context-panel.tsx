"use client";

import {
  Database,
  FileText,
  Code2,
  BarChart3,
  Layers,
  Hash,
  Cpu,
} from "lucide-react";
import { useRepositoryStore } from "@/stores/repository-store";

export function RepositoryContextPanel() {
  const context = useRepositoryStore((s) => s.context);
  const repository = useRepositoryStore((s) => s.repository);

  if (!context && !repository) return null;

  return (
    <section className="space-y-2">
      <div className="flex items-center justify-between">
        <p className="text-xs font-medium uppercase tracking-[0.12em] text-muted-foreground">
          Repository Context
        </p>
        <Database className="h-3.5 w-3.5 text-muted-foreground" />
      </div>

      {context ? (
        <div className="grid gap-2">
          {/* Retrieved Files */}
          {context.retrievedFiles.length > 0 && (
            <div className="rounded-md border border-border bg-secondary/20 px-3 py-2">
              <div className="mb-1.5 flex items-center gap-1.5 text-xs text-muted-foreground">
                <FileText className="h-3 w-3" />
                <span className="font-medium">Retrieved Files</span>
                <span className="ml-auto text-[10px]">
                  {context.retrievedFiles.length}
                </span>
              </div>
              <ul className="grid gap-0.5">
                {context.retrievedFiles
                  .filter((f, i, arr) => arr.indexOf(f) === i)
                  .slice(0, 8)
                  .map((file) => (
                    <li
                      key={file}
                      className="truncate text-[11px] leading-4 text-foreground font-mono"
                      title={file}
                    >
                      {file}
                    </li>
                  ))}
                {context.retrievedFiles.length > 8 && (
                  <li className="text-[10px] text-muted-foreground">
                    +{context.retrievedFiles.length - 8} more
                  </li>
                )}
              </ul>
            </div>
          )}

          {/* Retrieved Symbols */}
          {context.retrievedSymbols.length > 0 && (
            <div className="rounded-md border border-border bg-secondary/20 px-3 py-2">
              <div className="mb-1.5 flex items-center gap-1.5 text-xs text-muted-foreground">
                <Code2 className="h-3 w-3" />
                <span className="font-medium">Retrieved Symbols</span>
                <span className="ml-auto text-[10px]">
                  {context.retrievedSymbols.length}
                </span>
              </div>
              <div className="flex flex-wrap gap-1">
                {context.retrievedSymbols
                  .filter((s, i, arr) => arr.indexOf(s) === i)
                  .slice(0, 10)
                  .map((sym) => (
                    <span
                      key={sym}
                      className="inline-flex rounded border border-border bg-secondary/40 px-1.5 py-0.5 text-[10px] font-mono text-foreground"
                    >
                      {sym}
                    </span>
                  ))}
              </div>
            </div>
          )}

          {/* Metrics grid */}
          <div className="grid gap-2">
            {[
              {
                icon: BarChart3,
                label: "Similarity",
                value:
                  context.topSimilarity != null
                    ? `${(context.topSimilarity * 100).toFixed(1)}%`
                    : "—",
              },
              {
                icon: Layers,
                label: "Chunks Used",
                value: context.chunksUsed.toLocaleString(),
              },
              {
                icon: Hash,
                label: "Context Tokens",
                value: context.contextTokens.toLocaleString(),
              },
              {
                icon: Database,
                label: "Repository",
                value: context.repositoryName,
              },
              {
                icon: Cpu,
                label: "Embedding Model",
                value: context.embeddingModel,
              },
            ].map((item) => (
              <div
                className="flex min-h-11 items-center justify-between gap-3 rounded-md border border-border bg-secondary/20 px-3 py-2"
                key={item.label}
              >
                <span className="flex items-center gap-1.5 min-w-0 truncate text-xs text-muted-foreground">
                  <item.icon className="h-3 w-3 shrink-0" />
                  {item.label}
                </span>
                <span className="max-w-[150px] truncate text-right text-xs font-medium text-foreground">
                  {item.value}
                </span>
              </div>
            ))}
          </div>
        </div>
      ) : repository ? (
        <div className="rounded-md border border-border bg-secondary/20 px-3 py-3 text-xs text-muted-foreground">
          <div className="flex items-center gap-2">
            <Database className="h-4 w-4 text-accent/60" />
            Send a message to see repository context
          </div>
        </div>
      ) : null}
    </section>
  );
}
