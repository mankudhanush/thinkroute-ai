"use client";

import { useEffect } from "react";
import { CheckCircle2, XCircle } from "lucide-react";
import { useToastStore } from "@/stores/toast-store";

export function ToastNotifications() {
  const toasts = useToastStore((state) => state.toasts);
  const dismissToast = useToastStore((state) => state.dismissToast);

  useEffect(() => {
    const timers = toasts.map((toast) => window.setTimeout(() => dismissToast(toast.id), 4000));
    return () => timers.forEach(window.clearTimeout);
  }, [toasts, dismissToast]);

  if (toasts.length === 0) {
    return null;
  }

  return (
    <div className="fixed right-4 top-4 z-50 grid w-[min(360px,calc(100vw-2rem))] gap-2" role="status">
      {toasts.map((toast) => {
        const Icon = toast.tone === "success" ? CheckCircle2 : XCircle;
        const tone = toast.tone === "success"
          ? "border-emerald-400/40 text-emerald-200"
          : "border-destructive/50 text-destructive-foreground";

        return (
          <button
            className={`flex items-center gap-2 rounded-md border bg-secondary px-3 py-2 text-left text-sm shadow-lg ${tone}`}
            key={toast.id}
            onClick={() => dismissToast(toast.id)}
            type="button"
          >
            <Icon className="h-4 w-4 shrink-0" />
            <span>{toast.message}</span>
          </button>
        );
      })}
    </div>
  );
}
