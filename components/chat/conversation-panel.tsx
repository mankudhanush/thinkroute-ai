"use client";

import { MessageSquareText } from "lucide-react";
import { Composer } from "@/components/chat/composer";
import { MessageList } from "@/components/chat/message-list";
import { RepositoryChatHeader } from "@/components/chat/repository-chat-header";
import { Separator } from "@/components/ui/separator";
import { useModelStore } from "@/stores/model-store";
import { useProviderStore } from "@/stores/provider-store";
import { useSettingsStore } from "@/stores/settings-store";

export function ConversationPanel() {
  const selectedProviderId = useProviderStore((state) => state.selectedProviderId);
  const provider = useProviderStore((state) => state.providers.find((item) => item.id === selectedProviderId));
  const selectedModel = useModelStore((state) => state.selectedModel);
  const routingMode = useSettingsStore((state) => state.routingMode);
  const isAuto = routingMode === "auto";

  return (
    <section className="flex h-full min-h-[720px] flex-col lg:min-h-0">
      <header className="flex h-[73px] items-center justify-between gap-4 px-5">
        <div className="flex min-w-0 items-center gap-3">
          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md border border-border bg-secondary">
            <MessageSquareText className="h-4.5 w-4.5" />
          </div>
          <div className="min-w-0">
            <h2 className="truncate text-sm font-semibold">Conversation</h2>
            <p className="truncate text-xs text-muted-foreground">
              {isAuto
                ? "Auto Mode — intelligent routing"
                : `${provider?.name ?? "Select a provider"} / ${selectedModel?.name ?? "Select a model"}`}
            </p>
          </div>
        </div>
        <div className="hidden items-center gap-2 text-xs text-muted-foreground sm:flex">
          <span
            className={`h-2 w-2 rounded-full ${isAuto ? "bg-emerald-400" : "bg-accent"}`}
          />
          {isAuto ? "Auto" : "Manual"}
        </div>
      </header>
      <Separator />
      <RepositoryChatHeader />
      <div className="flex min-h-0 flex-1 overflow-y-auto">
        <MessageList />
      </div>
      <Composer />
    </section>
  );
}
