"use client";

import { motion } from "framer-motion";
import { Boxes, BrainCircuit, Building2, Network, Store } from "lucide-react";
import { fadeUp, stagger } from "@/components/landing/constants";
import { SectionHeading } from "@/components/landing/section-heading";

const VISION = [
  { icon: BrainCircuit, title: "Context Memory", desc: "Long-term memory that carries context across every session." },
  { icon: Network, title: "Learning Router", desc: "A router that improves its routing decisions over time." },
  { icon: Store, title: "AI Marketplace", desc: "Discover and plug in new models and providers instantly." },
  { icon: Boxes, title: "Multi-Agent Workflows", desc: "Orchestrate teams of specialized agents on one task." },
  { icon: Building2, title: "Enterprise Gateway", desc: "Governance, quotas, and audit-ready routing for teams." },
];

export function LandingFuture() {
  return (
    <section className="scroll-mt-24 px-5 py-20 sm:px-8">
      <div className="mx-auto max-w-7xl">
        {/* ── Side-by-side: cards left, heading right ── */}
        <div className="grid items-start gap-12 lg:grid-cols-[1.6fr_1fr] lg:gap-16">
          {/* Left: vision cards 2-col grid */}
          <motion.div
            variants={stagger}
            initial="hidden"
            whileInView="show"
            viewport={{ once: true, margin: "-80px" }}
            className="grid grid-cols-1 gap-4 sm:grid-cols-2"
          >
            {VISION.map((item) => (
              <motion.div
                key={item.title}
                variants={fadeUp}
                whileHover={{ y: -4 }}
                className="group relative overflow-hidden rounded-xl border border-[hsl(240,4%,18%)] bg-[hsl(240,5%,10%)] p-5"
              >
                <div className="absolute -left-8 -top-8 h-24 w-24 rounded-full bg-[hsl(193,58%,48%)]/15 opacity-0 blur-2xl transition-opacity duration-300 group-hover:opacity-100" />
                <div className="relative">
                  <div className="mb-3 flex items-center gap-3">
                    <span className="flex h-9 w-9 items-center justify-center rounded-md border border-[hsl(240,4%,18%)] bg-[hsl(240,4%,14%)]">
                      <item.icon className="h-4 w-4 text-[hsl(193,58%,48%)]" />
                    </span>
                    <span className="rounded-full border border-[hsl(240,4%,18%)] bg-[hsl(240,4%,14%)] px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide text-[hsl(240,5%,48%)]">
                      Roadmap
                    </span>
                  </div>
                  <h3 className="text-sm font-semibold text-white">{item.title}</h3>
                  <p className="mt-1.5 text-sm leading-5 text-[hsl(240,5%,60%)]">{item.desc}</p>
                </div>
              </motion.div>
            ))}
          </motion.div>

          {/* Right: sticky heading */}
          <div className="lg:sticky lg:top-24">
            <SectionHeading
              eyebrow="Future Vision"
              title="Where ThinkRoute is headed"
              description="An expanding platform built for the next generation of AI orchestration — smarter, faster, and more capable."
              align="left"
            />
          </div>
        </div>
      </div>
    </section>
  );
}
