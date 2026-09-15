"use client";

import { motion } from "framer-motion";
import { Check, X } from "lucide-react";
import { fadeUp, stagger } from "@/components/landing/constants";
import { SectionHeading } from "@/components/landing/section-heading";

const ROWS = [
  { instead: "Multiple AI Tabs", use: "One Unified Workspace" },
  { instead: "Manual Model Selection", use: "Automatic Routing" },
  { instead: "Lost Context", use: "Persistent Context" },
  { instead: "Single Provider", use: "Multi Provider" },
];

export function LandingWhy() {
  return (
    <section id="about" className="scroll-mt-24 px-5 py-20 sm:px-8">
      <div className="mx-auto max-w-7xl">
        {/* ── Side-by-side: heading left, comparison table right ── */}
        <div className="grid items-center gap-12 lg:grid-cols-[1fr_1.5fr] lg:gap-16">
          {/* Left: heading */}
          <div>
            <SectionHeading
              eyebrow="Why ThinkRoute"
              title="Stop juggling. Start routing."
              description="Replace the scattered, manual multi-model workflow with a single intelligent layer that just works."
              align="left"
            />
          </div>

          {/* Right: comparison table */}
          <motion.div
            variants={stagger}
            initial="hidden"
            whileInView="show"
            viewport={{ once: true, margin: "-80px" }}
            className="overflow-hidden rounded-2xl border border-[hsl(240,4%,18%)] bg-[hsl(240,5%,10%)]"
          >
            {/* Header */}
            <div className="grid grid-cols-2 border-b border-[hsl(240,4%,18%)] bg-[hsl(240,4%,14%)]">
              <div className="px-5 py-3.5 text-xs font-semibold uppercase tracking-wide text-[hsl(240,5%,55%)]">
                Instead of
              </div>
              <div className="border-l border-[hsl(240,4%,18%)] px-5 py-3.5 text-xs font-semibold uppercase tracking-wide text-white">
                With ThinkRoute AI
              </div>
            </div>

            {ROWS.map((row) => (
              <motion.div
                key={row.instead}
                variants={fadeUp}
                className="grid grid-cols-2 border-b border-[hsl(240,4%,18%)]/60 last:border-b-0"
              >
                <div className="flex items-center gap-3 px-5 py-4">
                  <X className="h-3.5 w-3.5 shrink-0 text-red-400/70" />
                  <span className="text-sm text-[hsl(240,5%,55%)] line-through decoration-white/20">
                    {row.instead}
                  </span>
                </div>
                <div className="flex items-center gap-3 border-l border-[hsl(240,4%,18%)] px-5 py-4">
                  <span className="flex h-4.5 w-4.5 shrink-0 items-center justify-center rounded-full bg-[hsl(193,58%,48%)]/15">
                    <Check className="h-2.5 w-2.5 text-[hsl(193,58%,48%)]" />
                  </span>
                  <span className="text-sm font-medium text-white">{row.use}</span>
                </div>
              </motion.div>
            ))}
          </motion.div>
        </div>
      </div>
    </section>
  );
}
