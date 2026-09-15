"use client";

import { motion } from "framer-motion";
import { Cpu, Route, Send, Sparkles } from "lucide-react";

const PROVIDERS = [
  { name: "Gemini", color: "hsl(193,58%,48%)", active: false },
  { name: "Groq", color: "#F97316", active: true },
  { name: "Cloudflare", color: "hsl(193,58%,65%)", active: false },
  { name: "Ollama", color: "#22C55E", active: false },
];

const METRICS = [
  { label: "Intent", value: "Code / Complex" },
  { label: "Provider", value: "Groq" },
  { label: "Confidence", value: "97%" },
  { label: "Response", value: "0.42s" },
];

// inline prop: when true, skip the extra outer motion wrapper (hero handles animation)
export function HeroPreview({ inline = false }: { inline?: boolean }) {
  const inner = (
    <div className="overflow-hidden rounded-xl border border-[hsl(240,4%,18%)] bg-[hsl(240,6%,7%)] shadow-[0_24px_80px_-16px_rgba(0,0,0,0.8)]">
      {/* Title bar */}
      <div className="flex items-center gap-3 border-b border-[hsl(240,4%,18%)] bg-[hsl(240,5%,10%)] px-4 py-3">
        <div className="flex gap-1.5">
          <span className="h-3 w-3 rounded-full bg-[#ff5f57]" />
          <span className="h-3 w-3 rounded-full bg-[#febc2e]" />
          <span className="h-3 w-3 rounded-full bg-[#28c840]" />
        </div>
        <div className="mx-auto flex items-center gap-2 rounded-md border border-[hsl(240,4%,18%)] bg-[hsl(240,4%,14%)] px-3 py-1 text-[11px] text-[hsl(240,5%,64%)]">
          <Route className="h-3 w-3 text-[hsl(193,58%,48%)]" />
          thinknroute.ai / workspace
        </div>
      </div>

      {/* Body: 3 panels */}
      <div className="grid grid-cols-1 gap-px bg-[hsl(240,4%,18%)] sm:grid-cols-[152px_1fr] lg:grid-cols-[152px_1fr_176px]">
        {/* Left: providers */}
        <div className="bg-[hsl(240,6%,7%)] p-4">
          <p className="mb-3 text-[10px] font-semibold uppercase tracking-[0.14em] text-[hsl(240,5%,42%)]">
            Providers
          </p>
          <div className="space-y-2">
            {PROVIDERS.map((p) => (
              <div
                key={p.name}
                className={`flex items-center gap-2 rounded-md border px-2.5 py-2 text-xs ${
                  p.active
                    ? "border-[hsl(193,58%,48%)]/40 bg-[hsl(193,58%,48%)]/10 text-white"
                    : "border-[hsl(240,4%,18%)] bg-[hsl(240,5%,10%)] text-[hsl(240,5%,62%)]"
                }`}
              >
                <span className="h-2 w-2 rounded-full" style={{ background: p.color, boxShadow: `0 0 6px ${p.color}` }} />
                {p.name}
              </div>
            ))}
          </div>
        </div>

        {/* Centre: conversation */}
        <div className="flex flex-col gap-3 bg-[hsl(240,6%,7%)] p-4">
          <div className="ml-auto max-w-[80%] rounded-xl rounded-br-sm border border-[hsl(240,4%,18%)] bg-[hsl(240,5%,10%)] px-3 py-2 text-xs text-white/90">
            Refactor this function and explain the time complexity.
          </div>

          <motion.div
            animate={{ opacity: [0.5, 1, 0.5] }}
            transition={{ duration: 2, repeat: Infinity, ease: "easeInOut" }}
            className="flex items-center gap-2 self-start rounded-full border border-[hsl(193,58%,48%)]/30 bg-[hsl(193,58%,48%)]/10 px-3 py-1 text-[11px] text-[hsl(193,58%,65%)]"
          >
            <Sparkles className="h-3 w-3 text-[hsl(193,58%,48%)]" />
            Auto-routing → Groq
          </motion.div>

          <div className="max-w-[85%] space-y-1.5 rounded-xl rounded-bl-sm border border-[hsl(240,4%,18%)] bg-[hsl(240,5%,10%)] px-3 py-2.5">
            <div className="h-2 w-[90%] rounded-full bg-white/[0.1]" />
            <div className="h-2 w-[70%] rounded-full bg-white/[0.07]" />
            <div className="h-2 w-[80%] rounded-full bg-white/[0.05]" />
          </div>

          <div className="mt-auto flex items-center gap-2 rounded-md border border-[hsl(240,4%,18%)] bg-[hsl(240,4%,14%)]/40 px-3 py-2">
            <span className="text-xs text-[hsl(240,5%,42%)]">Ask anything…</span>
            <span className="ml-auto flex h-6 w-6 items-center justify-center rounded-md border border-[hsl(193,58%,48%)]/40 bg-[hsl(193,58%,48%)]/20">
              <Send className="h-3 w-3 text-[hsl(193,58%,48%)]" />
            </span>
          </div>
        </div>

        {/* Right: metrics */}
        <div className="hidden bg-[hsl(240,6%,7%)] p-4 lg:block">
          <p className="mb-3 flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-[0.14em] text-[hsl(240,5%,42%)]">
            <Cpu className="h-3 w-3" />
            Inference
          </p>
          <div className="space-y-2">
            {METRICS.map((m) => (
              <div key={m.label} className="rounded-md border border-[hsl(240,4%,18%)] bg-[hsl(240,5%,10%)] px-2.5 py-2">
                <p className="text-[10px] uppercase tracking-wide text-[hsl(240,5%,42%)]">{m.label}</p>
                <p className="mt-0.5 text-xs font-medium text-white">{m.value}</p>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );

  if (inline) return inner;

  return (
    <motion.div
      initial={{ opacity: 0, y: 24 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.7, delay: 0.35, ease: [0.21, 0.47, 0.32, 0.98] }}
      className="relative mx-auto w-full max-w-4xl"
    >
      <div
        className="pointer-events-none absolute -inset-4 -z-10 rounded-[28px] blur-2xl"
        style={{ background: "radial-gradient(ellipse at center, rgba(49,180,200,0.18), transparent 70%)" }}
      />
      {inner}
    </motion.div>
  );
}
