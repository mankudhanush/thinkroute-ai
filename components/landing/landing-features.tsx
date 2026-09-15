"use client";

import { motion } from "framer-motion";
import {
  Activity,
  Brain,
  Lock,
  MessagesSquare,
  RefreshCw,
  Zap,
} from "lucide-react";
import { fadeUp, stagger } from "@/components/landing/constants";
import { SectionHeading } from "@/components/landing/section-heading";

const FEATURES = [
  { icon: Brain, title: "Intelligent Routing", desc: "Chooses the best AI model automatically for every prompt." },
  { icon: Zap, title: "Lightning Fast", desc: "Low-latency intelligent orchestration across providers." },
  { icon: RefreshCw, title: "Automatic Failover", desc: "Switches providers automatically when one is unavailable." },
  { icon: MessagesSquare, title: "Context Aware", desc: "Relevant memory retrieval keeps every conversation coherent." },
  { icon: Lock, title: "Privacy First", desc: "Local models supported for fully private inference." },
  { icon: Activity, title: "Analytics", desc: "Provider usage insights and live inference metrics." },
];

export function LandingFeatures() {
  return (
    <section id="features" className="scroll-mt-24 px-5 py-20 sm:px-8">
      <div className="mx-auto max-w-7xl">
        {/* ── Side-by-side: heading left (sticky), 3×2 grid right ── */}
        <div className="grid items-start gap-12 lg:grid-cols-[1fr_1.8fr] lg:gap-16">
          {/* Left: sticky heading */}
          <div className="lg:sticky lg:top-24">
            <SectionHeading
              eyebrow="Features"
              title="Everything you need to orchestrate AI"
              description="A production-grade routing layer with the controls and observability serious workflows demand."
              align="left"
            />
          </div>

          {/* Right: 3-column feature cards */}
          <motion.div
            variants={stagger}
            initial="hidden"
            whileInView="show"
            viewport={{ once: true, margin: "-80px" }}
            className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-2"
          >
            {FEATURES.map((feature) => (
              <motion.div
                key={feature.title}
                variants={fadeUp}
                whileHover={{ y: -4 }}
                className="group relative overflow-hidden rounded-xl border border-[hsl(240,4%,18%)] bg-[hsl(240,5%,10%)] p-5 transition-colors hover:border-[hsl(193,58%,48%)]/40"
              >
                <div className="absolute inset-x-0 -top-px h-px bg-gradient-to-r from-transparent via-[hsl(193,58%,48%)]/60 to-transparent opacity-0 transition-opacity duration-300 group-hover:opacity-100" />
                <span className="flex h-10 w-10 items-center justify-center rounded-md border border-[hsl(240,4%,18%)] bg-[hsl(240,4%,14%)] transition-colors group-hover:border-[hsl(193,58%,48%)]/40">
                  <feature.icon className="h-4.5 w-4.5 text-[hsl(193,58%,48%)]" />
                </span>
                <h3 className="mt-3 text-sm font-semibold text-white">{feature.title}</h3>
                <p className="mt-1.5 text-sm leading-6 text-[hsl(240,5%,60%)]">{feature.desc}</p>
              </motion.div>
            ))}
          </motion.div>
        </div>
      </div>
    </section>
  );
}
