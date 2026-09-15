"use client";

import { FormEvent, useEffect, useState } from "react";
import { LoaderCircle, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ApiError } from "@/services/api-client";
import { useProviderStore } from "@/stores/provider-store";
import { useToastStore } from "@/stores/toast-store";
import type { Provider } from "@/types/provider";

interface ProviderConnectDialogProps {
  provider: Provider | null;
  onClose: () => void;
  onConnected: (provider: Provider) => void;
}

function supportsBaseUrl(provider: Provider) {
  return provider.id === "cloudflare" || provider.id === "ollama";
}

export function ProviderConnectDialog({
  provider,
  onClose,
  onConnected,
}: ProviderConnectDialogProps) {
  const [apiKey, setApiKey] = useState("");
  const [baseUrl, setBaseUrl] = useState("");
  const [error, setError] = useState<string | null>(null);
  const connectProvider = useProviderStore((state) => state.connectProvider);
  const connectingProviderId = useProviderStore((state) => state.connectingProviderId);
  const showToast = useToastStore((state) => state.showToast);
  const isConnecting = Boolean(provider && connectingProviderId === provider.id);

  useEffect(() => {
    setApiKey("");
    setBaseUrl("");
    setError(null);
  }, [provider]);

  if (!provider) {
    return null;
  }

  const activeProvider = provider;
  const needsApiKey = activeProvider.id !== "ollama";

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);

    try {
      await connectProvider({
        provider: activeProvider.id,
        apiKey: apiKey.trim() || undefined,
        baseUrl: baseUrl.trim() || undefined,
      });
      showToast("Connected Successfully", "success");
      onConnected(activeProvider);
      onClose();
    } catch (caughtError) {
      const message = caughtError instanceof ApiError ? caughtError.message : "Unable to connect provider";
      setError(message);
      showToast(message, "error");
    }
  }

  return (
    <div
      aria-modal="true"
      className="fixed inset-0 z-40 flex items-center justify-center bg-black/60 px-4"
      onMouseDown={onClose}
      role="dialog"
    >
      <form
        className="w-full max-w-md rounded-md border border-border bg-background p-5 shadow-xl"
        onMouseDown={(event) => event.stopPropagation()}
        onSubmit={handleSubmit}
      >
        <div className="flex items-start justify-between gap-3">
          <div>
            <p className="text-sm font-semibold">Connect {activeProvider.name}</p>
            <p className="mt-1 text-xs text-muted-foreground">Credentials are validated by the selected provider.</p>
          </div>
          <Button aria-label="Close connection dialog" onClick={onClose} size="icon" type="button" variant="ghost">
            <X className="h-4 w-4" />
          </Button>
        </div>

        <div className="mt-5 grid gap-4">
          <label className="grid gap-1.5 text-sm">
            <span>API Key</span>
            <input
              autoComplete="off"
              className="h-9 rounded-md border border-input bg-background px-3 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring"
              disabled={isConnecting}
              onChange={(event) => setApiKey(event.target.value)}
              required={needsApiKey}
              type="password"
              value={apiKey}
            />
          </label>

          {supportsBaseUrl(activeProvider) ? (
            <label className="grid gap-1.5 text-sm">
              <span>{activeProvider.id === "ollama" ? "Ollama URL" : "Account ID (or full API URL)"}</span>
              <input
                className="h-9 rounded-md border border-input bg-background px-3 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring"
                disabled={isConnecting}
                onChange={(event) => setBaseUrl(event.target.value)}
                placeholder={activeProvider.id === "ollama" ? "http://localhost:11434" : "Cloudflare Account ID (or full API URL)"}
                type="text"
                value={baseUrl}
              />
            </label>
          ) : null}
        </div>

        {error ? <p className="mt-4 text-sm text-destructive">{error}</p> : null}

        <div className="mt-6 flex justify-end gap-2">
          <Button disabled={isConnecting} onClick={onClose} type="button" variant="ghost">
            Cancel
          </Button>
          <Button disabled={isConnecting} type="submit">
            {isConnecting ? <LoaderCircle className="h-4 w-4 animate-spin" /> : null}
            Connect
          </Button>
        </div>
      </form>
    </div>
  );
}
