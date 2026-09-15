"use client";

import { create } from "zustand";
import type { RoutingMode } from "@/types/inference";

interface SettingsStore {
  routingMode: RoutingMode;
  setRoutingMode: (routingMode: RoutingMode) => void;
}

export const useSettingsStore = create<SettingsStore>((set) => ({
  routingMode: "manual",
  setRoutingMode: (routingMode) => set({ routingMode }),
}));
