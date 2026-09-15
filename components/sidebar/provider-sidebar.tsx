import { BrainCircuit, Sparkles } from "lucide-react";
import { ProviderList } from "@/components/providers/provider-list";
import { ModelPicker } from "@/components/providers/model-picker";
import { RoutingModeToggle } from "@/components/routing/routing-mode-toggle";
import { RepositoryWorkspace } from "@/components/sidebar/repository-workspace";
import { Separator } from "@/components/ui/separator";
import { useSettingsStore } from "@/stores/settings-store";

export function ProviderSidebar() {
  const routingMode = useSettingsStore((state) => state.routingMode);
  const isAuto = routingMode === "auto";

  return (
    <aside className="flex h-full min-h-[720px] flex-col px-4 py-4 lg:min-h-0">
      <header className="flex h-14 items-center gap-3">
        <div className="flex h-9 w-9 items-center justify-center rounded-md border border-border bg-secondary">
          <BrainCircuit className="h-4.5 w-4.5" />
        </div>
        <div className="min-w-0">
          <h1 className="truncate text-sm font-semibold">ThinkRoute AI</h1>
          <p className="truncate text-xs text-muted-foreground">
            {isAuto ? "Intelligent auto-routing" : "Manual inference routing"}
          </p>
        </div>
      </header>
      <Separator className="my-3" />
      <div className="flex-1 space-y-6 overflow-y-auto pb-2 pr-1">
        <RoutingModeToggle />
        {isAuto ? (
          <>
            <div className="space-y-2">
              <p className="text-xs font-medium uppercase tracking-[0.12em] text-muted-foreground">
                Auto Mode
              </p>
              <div className="rounded-md border border-border bg-accent/5 px-3 py-3">
                <div className="flex items-center gap-2 text-sm font-medium text-foreground">
                  <Sparkles className="h-4 w-4 text-accent" />
                  Intelligent Routing Active
                </div>
                <p className="mt-2 text-xs leading-5 text-muted-foreground">
                  ThinkRoute will automatically analyze your prompt, classify your intent, and route to the best provider and model. Just type and send.
                </p>
              </div>
            </div>
            <RepositoryWorkspace />
          </>
        ) : (
          <>
            <ProviderList />
            <ModelPicker />
          </>
        )}
      </div>
    </aside>
  );
}
