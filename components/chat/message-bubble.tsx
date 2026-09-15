"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import { motion } from "framer-motion";
import ReactMarkdown from "react-markdown";
import type { Components } from "react-markdown";
import { formatRelativeTime } from "@/lib/utils";
import { useProviderStore } from "@/stores/provider-store";
import { useStreamingStore } from "@/stores/streaming-store";
import { useStreamingText } from "@/hooks/use-streaming-text";
import { useChatStore } from "@/stores/chat-store";
import { useModelStore } from "@/stores/model-store";
import { useSettingsStore } from "@/stores/settings-store";
import type { ChatMessage } from "@/types/chat";

interface MessageBubbleProps {
  message: ChatMessage;
  isLatestAssistant?: boolean;
}

const PROVIDER_LABELS: Record<string, string> = {
  gemini: "Google Gemini",
  groq: "Groq",
  cloudflare: "Cloudflare Workers AI",
  ollama: "Ollama",
};

/* ─────────────────────────────────────────────
 * Code block with language header + copy button
 * ───────────────────────────────────────────── */
function CodeBlockCopy({ code }: { code: string }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = () => {
    navigator.clipboard.writeText(code).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  };

  return (
    <button
      className={`code-copy-btn${copied ? " copied" : ""}`}
      onClick={handleCopy}
      type="button"
    >
      {copied ? "✓ Copied" : "Copy"}
    </button>
  );
}

function markdownComponents(): Components {
  return {
    pre({ children, ...props }) {
      // Extract the <code> child to get lang + text
      const codeChild = Array.isArray(children)
        ? children.find(
            (child: unknown) =>
              typeof child === "object" &&
              child !== null &&
              "type" in child &&
              (child as { type: string }).type === "code",
          )
        : typeof children === "object" &&
            children !== null &&
            "type" in children &&
            (children as { type: string }).type === "code"
          ? children
          : null;

      if (!codeChild || typeof codeChild !== "object" || !("props" in codeChild)) {
        return <pre {...props}>{children}</pre>;
      }

      const codeProps = (codeChild as { props: { className?: string; children?: string } }).props;
      const className = codeProps.className ?? "";
      const match = /language-(\w+)/.exec(className);
      const lang = match ? match[1] : "";
      const codeText =
        typeof codeProps.children === "string"
          ? codeProps.children.replace(/\n$/, "")
          : "";

      return (
        <div className="code-block-wrapper">
          <div className="code-block-header">
            <span className="lang-label">{lang || "code"}</span>
            <CodeBlockCopy code={codeText} />
          </div>
          <pre {...props}>{children}</pre>
        </div>
      );
    },
  };
}

/* ─────────────────────────────────────────────
 * Edit Prompt (user messages only)
 * ───────────────────────────────────────────── */
function EditableUserMessage({
  message,
  onCancel,
}: {
  message: ChatMessage;
  onCancel: () => void;
}) {
  const [editText, setEditText] = useState(message.content);
  const sendMessage = useChatStore((state) => state.sendMessage);
  const messages = useChatStore((state) => state.messages);
  const selectedModel = useModelStore((state) => state.selectedModel);
  const routingMode = useSettingsStore((state) => state.routingMode);
  const isAuto = routingMode === "auto";

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    const trimmed = editText.trim();
    if (!trimmed) return;

    // Remove messages from this message onward (ChatGPT-style edit behavior)
    const msgIndex = messages.findIndex((m) => m.id === message.id);
    if (msgIndex !== -1) {
      useChatStore.setState({
        messages: messages.slice(0, msgIndex),
      });
    }

    // Re-send with edited content
    sendMessage({
      content: trimmed,
      modelId: isAuto ? null : (selectedModel?.id ?? null),
      providerId: isAuto ? null : (selectedModel?.providerId ?? null),
    });

    onCancel();
  };

  return (
    <form onSubmit={handleSubmit}>
      <textarea
        className="edit-textarea"
        value={editText}
        onChange={(e) => setEditText(e.target.value)}
        rows={3}
        autoFocus
      />
      <div className="edit-actions">
        <button
          type="submit"
          className="msg-action-btn"
          style={{
            background: "hsl(var(--accent))",
            color: "hsl(var(--accent-foreground))",
            padding: "5px 14px",
            borderRadius: "6px",
            fontWeight: 500,
          }}
        >
          Save & Submit
        </button>
        <button
          type="button"
          className="msg-action-btn"
          onClick={onCancel}
        >
          Cancel
        </button>
      </div>
    </form>
  );
}

/* ─────────────────────────────────────────────
 * Main MessageBubble
 * ───────────────────────────────────────────── */
export function MessageBubble({ message, isLatestAssistant = false }: MessageBubbleProps) {
  const provider = useProviderStore((state) => state.providers.find((item) => item.id === message.providerId));
  const model = provider?.availableModels.find((item) => item.id === message.modelId);
  const isUser = message.role === "user";
  const routing = message.routing;
  const context = message.context;

  // ── Streaming ──
  const shouldStream = isLatestAssistant && !isUser && message.status === "complete";
  const { displayedText, isStreaming, stop } = useStreamingText(message.content, {
    enabled: shouldStream,
  });

  const setStreamingState = useStreamingStore((state) => state.setStreaming);
  const setStopper = useStreamingStore((state) => state.setStopper);

  useEffect(() => {
    if (shouldStream) {
      setStreamingState(isStreaming);
      setStopper(isStreaming ? stop : null);
    }
    return () => {
      if (shouldStream) {
        setStreamingState(false);
        setStopper(null);
      }
    };
  }, [isStreaming, shouldStream, setStreamingState, setStopper, stop]);

  const textToRender = shouldStream ? displayedText : message.content;

  // ── Copy response ──
  const [copied, setCopied] = useState(false);
  const handleCopy = useCallback(() => {
    navigator.clipboard.writeText(message.content).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  }, [message.content]);

  // ── Edit prompt ──
  const [isEditing, setIsEditing] = useState(false);

  // ── Components for ReactMarkdown (with code block headers) ──
  const mdComponents = markdownComponents();

  return (
    <motion.article
      animate={{ opacity: 1, y: 0 }}
      className="group grid gap-2"
      initial={{ opacity: 0, y: 8 }}
      transition={{ duration: 0.18 }}
    >
      <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
        <span className="font-medium text-foreground">
          {isUser ? "You" : provider?.name ?? message.providerId ?? "Assistant"}
        </span>
        <span>{formatRelativeTime(new Date(message.createdAt))}</span>
        {message.modelId ? <span>{model?.name ?? message.modelId}</span> : null}
      </div>

      {/* Message body */}
      {isUser && isEditing ? (
        <EditableUserMessage message={message} onCancel={() => setIsEditing(false)} />
      ) : (
        <div
          className={`markdown-body max-w-[860px] rounded-md border border-border bg-secondary/35 px-4 py-3 text-sm leading-6 shadow-sm${
            isStreaming ? " streaming-cursor" : ""
          }`}
        >
          <ReactMarkdown components={mdComponents}>{textToRender}</ReactMarkdown>
        </div>
      )}

      {/* Action buttons */}
      {!isEditing && (
        <div className="msg-actions">
          {isUser ? (
            <button
              type="button"
              className="msg-action-btn"
              onClick={() => setIsEditing(true)}
            >
              ✏️ Edit
            </button>
          ) : (
            <button
              type="button"
              className={`msg-action-btn${copied ? " copied-feedback" : ""}`}
              onClick={handleCopy}
            >
              {copied ? "✓ Copied" : "📋 Copy"}
            </button>
          )}
        </div>
      )}

      {/* Routing badges (unchanged) */}
      {!isUser && routing ? (
        <div className="space-y-1.5">
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="inline-flex items-center gap-1 rounded-md border border-accent/25 bg-accent/8 px-2 py-0.5 text-[10px] font-medium text-accent">
              Routed to {PROVIDER_LABELS[routing.provider] ?? routing.provider}
            </span>
            <span className="inline-flex items-center gap-1 rounded-md border border-border bg-secondary/40 px-2 py-0.5 text-[10px] font-medium text-muted-foreground capitalize">
              Intent: {routing.intent.replace("_", " ")}
            </span>
            <span className="inline-flex items-center gap-1 rounded-md border border-border bg-secondary/40 px-2 py-0.5 text-[10px] font-medium text-muted-foreground capitalize">
              {routing.complexity}
            </span>
            <span className="inline-flex items-center gap-1 rounded-md border border-border bg-secondary/40 px-2 py-0.5 text-[10px] font-medium text-muted-foreground">
              {Math.round(routing.confidence * 100)}%
            </span>
            {typeof routing.total_ms === "number" && routing.total_ms > 0 ? (
              <span className="inline-flex items-center gap-1 rounded-md border border-border bg-secondary/40 px-2 py-0.5 text-[10px] font-medium text-muted-foreground">
                {(routing.total_ms / 1000).toFixed(2)}s
              </span>
            ) : null}
          </div>
          {routing.reason ? (
            <p className="text-[10px] leading-4 text-muted-foreground/70 italic pl-0.5">
              {routing.reason}
            </p>
          ) : null}
        </div>
      ) : null}
      {!isUser && context ? <ContextChip context={context} /> : null}
    </motion.article>
  );
}

function ContextChip({ context }: { context: NonNullable<ChatMessage["context"]> }) {
  if (!context.used) {
    return (
      <div className="flex items-center gap-1.5 pl-0.5 text-[10px] text-muted-foreground/70">
        <span>🧠</span>
        <span>No previous context used{context.is_new_topic ? " — new topic" : ""}.</span>
      </div>
    );
  }

  return (
    <div className="space-y-1 rounded-md border border-accent/20 bg-accent/5 px-2.5 py-1.5">
      <div className="flex items-center gap-1.5 text-[10px] font-medium text-accent">
        <span>🧠</span>
        <span>
          Context Used — {context.used_count} of {context.total_history} prior message
          {context.total_history !== 1 ? "s" : ""}
        </span>
      </div>
      <ul className="grid gap-0.5">
        {context.messages
          .filter((m) => m.role === "user")
          .map((m, i) => (
            <li
              className="truncate text-[10px] leading-4 text-muted-foreground"
              key={`${i}-${m.content.slice(0, 12)}`}
              title={m.content}
            >
              • {m.content}
            </li>
          ))}
      </ul>
    </div>
  );
}
