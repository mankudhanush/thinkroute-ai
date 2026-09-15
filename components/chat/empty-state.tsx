import { ArrowUpRight, MessagesSquare, Route } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { TypingIndicator } from "@/components/chat/typing-indicator";

export function EmptyState() {
  return (
    <div className="mx-auto flex max-w-2xl flex-1 flex-col justify-center px-6 py-10">
      <div className="mb-5 flex h-11 w-11 items-center justify-center rounded-md border border-border bg-secondary">
        <MessagesSquare className="h-5 w-5" />
      </div>
      <div className="space-y-3">
        <div className="flex flex-wrap items-center gap-2">
          <Badge variant="accent">Manual mode</Badge>
          <Badge variant="muted">Backend-ready</Badge>
        </div>
        <h2 className="max-w-xl text-2xl font-semibold tracking-normal text-foreground md:text-3xl">
          Start a routed conversation with the selected model.
        </h2>
        <p className="max-w-xl text-sm leading-6 text-muted-foreground">
          Connect a provider, select one of its available models, and send your first message.
        </p>
      </div>
      <div className="mt-8 grid gap-2 text-sm text-muted-foreground sm:grid-cols-2">
        <div className="flex items-center gap-2 rounded-md border border-border bg-secondary/25 px-3 py-2.5">
          <Route className="h-4 w-4 text-accent" />
          Single selected model per message
        </div>
        <div className="flex items-center gap-2 rounded-md border border-border bg-secondary/25 px-3 py-2.5">
          <ArrowUpRight className="h-4 w-4 text-accent" />
          Streaming UI surfaces prepared
        </div>
      </div>
      <div className="mt-7 text-xs text-muted-foreground">
        <TypingIndicator className="mr-2 align-middle" />
        Waiting for input
      </div>
    </div>
  );
}
