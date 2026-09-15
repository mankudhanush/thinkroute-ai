"use client";

import { create } from "zustand";

export type ToastTone = "success" | "error";

export interface ToastMessage {
  id: string;
  message: string;
  tone: ToastTone;
}

interface ToastStore {
  toasts: ToastMessage[];
  showToast: (message: string, tone: ToastTone) => void;
  dismissToast: (id: string) => void;
}

export const useToastStore = create<ToastStore>((set) => ({
  toasts: [],
  showToast: (message, tone) =>
    set((state) => ({
      toasts: [...state.toasts, { id: crypto.randomUUID(), message, tone }],
    })),
  dismissToast: (id) =>
    set((state) => ({ toasts: state.toasts.filter((toast) => toast.id !== id) })),
}));
