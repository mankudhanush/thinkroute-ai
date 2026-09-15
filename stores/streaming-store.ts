"use client";

import { create } from "zustand";

interface StreamingStore {
  /** Whether an assistant message is currently being streamed */
  isStreaming: boolean;
  /** The stop function registered by the active streaming bubble */
  stopFn: (() => void) | null;
  /** Called by MessageBubble when streaming starts */
  setStreaming: (isStreaming: boolean) => void;
  /** Called by MessageBubble to register its stop callback */
  setStopper: (fn: (() => void) | null) => void;
  /** Called by Composer to stop the current stream */
  stop: () => void;
}

export const useStreamingStore = create<StreamingStore>((set, get) => ({
  isStreaming: false,
  stopFn: null,
  setStreaming: (isStreaming) => set({ isStreaming }),
  setStopper: (fn) => set({ stopFn: fn }),
  stop: () => {
    const { stopFn } = get();
    if (stopFn) {
      stopFn();
    }
    set({ isStreaming: false, stopFn: null });
  },
}));
