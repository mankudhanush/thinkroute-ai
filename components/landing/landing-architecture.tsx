"use client";

import { motion } from "framer-motion";
import { Cloud, Cpu, Sparkles, User, Waypoints, Zap } from "lucide-react";
import { fadeUp } from "@/components/landing/constants";
import { SectionHeading } from "@/components/landing/section-heading";

const PROVIDERS = [
  { name: "Gemini", icon: Sparkles },
  { name: "Groq", icon: Zap },
  { name: "Cloudflare", icon: Cloud },
  { name: "Ollama", icon: Cpu },
];

function FlowNode({
  icon: Icon,
  label,
  highlight,
}: {
  icon: React.ComponentType<{ className?: string }>;
  label: string;
  highlight?: boolean;
}) {
  return (
    <div
      className={`flex w-full max-w-xs items-center gap-3 rounded-xl border px-5 py-3.5 ${
        highlight
          ? "border-[hsl(193,58%,48%)]/50 bg-[hsl(193,58%,48%)]/10 shadow-[0_0_24px_-8px_rgba(49,180,200,0.7)]"
          : "border-[hsl(240,4%,18%)] bg-[hsl(240,5%,10%)]"
      }`}
    >
      <span
        className={`flex h-9 w-9 items-center justify-center rounded-md ${
          highlight
            ? "border border-[hsl(193,58%,48%)]/50 bg-[hsl(193,58%,48%)]/20"
            : "border border-[hsl(240,4%,18%)] bg-[hsl(240,4%,14%)]"
        }`}
      >
        <Icon className={`h-4.5 w-4.5 ${highlight ? "text-[hsl(193,58%,65%)]" : "text-[hsl(240,5%,60%)]"}`} />
      </span>
      <span className="text-sm font-semibold text-white">{label}</span>
    </div>
  );
}

function Connector() {
  return (
    <motion.div
      animate={{ opacity: [0.3, 1, 0.3] }}
      transition={{ duration: 1.8, repeat: Infinity, ease: "easeInOut" }}
      className="mx-auto my-1.5 h-7 w-px"
      style={{ background: "linear-gradient(to bottom, hsl(193,58%,48%), hsl(193,58%,65%))" }}
    />
  );
}

export function LandingArchitecture() {
  return (
    <section id="architecture" className="scroll-mt-24 px-5 py-20 sm:px-8">
      <div className="mx-auto max-w-7xl">
        {/* ── Side-by-side: flow diagram left, heading right ── */}
        <div className="grid items-center gap-12 lg:grid-cols-2 lg:gap-16">
          {/* Left: flow diagram */}
          <motion.div
            variants={fadeUp}
            initial="hidden"
            whileInView="show"
            viewport={{ once: true, margin: "-80px" }}
            className="relative overflow-hidden rounded-2xl border border-[hsl(240,4%,18%)] bg-[hsl(240,5%,10%)] p-8 sm:p-10"
          >
            <div
              className="pointer-events-none absolute inset-0"
              style={{ background: "radial-gradient(circle at center, rgba(49,180,200,0.06), transparent 65%)" }}
            />
            <div className="relative flex flex-col items-center">
              <FlowNode icon={User} label="User" />
              <Connector />
              <FlowNode icon={Waypoints} label="ThinkRoute AI" highlight />
              <Connector />
              <FlowNode icon={Waypoints} label="Routing Engine" />
              <Connector />
              <div className="grid w-full max-w-xs grid-cols-2 gap-2.5">
                {PROVIDERS.map((p) => (
                  <div
                    key={p.name}
                    className="flex flex-col items-center gap-2 rounded-xl border border-[hsl(240,4%,18%)] bg-[hsl(240,6%,7%)] px-3 py-4"
                  >
                    <span className="flex h-9 w-9 items-center justify-center rounded-md border border-[hsl(240,4%,18%)] bg-[hsl(240,4%,14%)]">
                      <p.icon className="h-4 w-4 text-[hsl(193,58%,48%)]" />
                    </span>
                    <span className="text-xs font-medium text-white">{p.name}</span>
                  </div>
                ))}
              </div>
            </div>
          </motion.div>

          {/* Right: heading */}
          <div>
            <SectionHeading
              eyebrow="Architecture"
              title="A routing engine at the core"
              description="ThinkRoute sits between you and the model layer, orchestrating every request through a single intelligent gateway. One integration. Every provider."
              align="left"
            />
          </div>
        </div>
      </div>
    </section>
  );
}
