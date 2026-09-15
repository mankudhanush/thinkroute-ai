"use client";

import { Badge } from "@/components/ui/badge";
import { useSettingsStore } from "@/stores/settings-store";
import type { RoutingMode } from "@/types/inference";

export function RoutingModeToggle() {
  const routingMode = useSettingsStore((state) => state.routingMode);
  const setRoutingMode = useSettingsStore((state) => state.setRoutingMode);

  function handleChange(mode: RoutingMode) {
    setRoutingMode(mode);
  }

  return (
    <div className="space-y-2">
      <p className="text-xs font-medium uppercase tracking-[0.12em] text-muted-foreground">
        Routing Mode
      </p>
      <div className="grid gap-2">
        <label
          className="flex cursor-pointer items-center justify-between rounded-md border border-border bg-secondary/35 px-3 py-2.5 text-sm transition-colors hover:bg-secondary/50"
          onClick={() => handleChange("manual")}
        >
          <span className="flex items-center gap-2">
            <input
              checked={routingMode === "manual"}
              className="h-3.5 w-3.5 accent-white"
              onChange={() => handleChange("manual")}
              suppressHydrationWarning
              type="radio"
              name="routing-mode"
            />
            Manual
          </span>
          <Badge variant={routingMode === "manual" ? "accent" : "muted"}>
            {routingMode === "manual" ? "Active" : ""}
          </Badge>
        </label>
        <label
          className="flex cursor-pointer items-center justify-between rounded-md border border-border bg-secondary/35 px-3 py-2.5 text-sm transition-colors hover:bg-secondary/50"
          onClick={() => handleChange("auto")}
        >
          <span className="flex items-center gap-2">
            <input
              checked={routingMode === "auto"}
              className="h-3.5 w-3.5 accent-white"
              onChange={() => handleChange("auto")}
              suppressHydrationWarning
              type="radio"
              name="routing-mode"
            />
            Auto
          </span>
          <Badge variant={routingMode === "auto" ? "accent" : "muted"}>
            {routingMode === "auto" ? "Active" : ""}
          </Badge>
        </label>
      </div>
    </div>
  );
}
