"use client";

import { motion } from "framer-motion";
import { Brain, ChevronRight, MessageSquare, Route, Send, Sparkles } from "lucide-react";
import { fadeUp, stagger } from "@/components/landing/constants";
import { SectionHeading } from "@/components/landing/section-heading";

const STEPS = [
  { icon: MessageSquare, title: "User Prompt", desc: "You send a single message." },
  { icon: Brain, title: "Intent Analysis", desc: "The prompt is classified by intent and complexity." },
  { icon: Route, title: "Smart Routing", desc: "The engine scores and selects the ideal model." },
  { icon: Sparkles, title: "Best AI Provider", desc: "The request is dispatched to the winning provider." },
  { icon: Send, title: "Response", desc: "A streamed answer returns — context preserved." },
];

export function LandingHowItWorks() {
  return (
    <section className="scroll-mt-24 px-5 py-20 sm:px-8">
      <div className="mx-auto max-w-7xl">
        {/* ── Side-by-side: steps left, heading right ── */}
        <div className="grid items-center gap-12 lg:grid-cols-2 lg:gap-16">
          {/* Left: step pipeline */}
          <motion.div
            variants={stagger}
            initial="hidden"
            whileInView="show"
            viewport={{ once: true, margin: "-60px" }}
            className="flex flex-col gap-3"
          >
            {STEPS.map((step, i) => (
              <motion.div key={step.title} variants={fadeUp} className="flex items-center gap-4">
                <div className="flex items-center gap-4 flex-1 rounded-xl border border-[hsl(240,4%,18%)] bg-[hsl(240,5%,10%)] px-5 py-4">
                  <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-md border border-[hsl(193,58%,48%)]/30 bg-[hsl(193,58%,48%)]/10">
                    <step.icon className="h-4.5 w-4.5 text-[hsl(193,58%,48%)]" />
                  </span>
                  <div>
                    <p className="text-sm font-semibold text-white">{step.title}</p>
                    <p className="text-xs text-[hsl(240,5%,60%)]">{step.desc}</p>
                  </div>
                </div>
                {i < STEPS.length - 1 && (
                  <motion.span
                    animate={{ x: [0, 4, 0], opacity: [0.4, 1, 0.4] }}
                    transition={{ duration: 1.6, repeat: Infinity, ease: "easeInOut" }}
                    className="shrink-0 text-[hsl(193,58%,48%)]"
                  >
                    {/* We use a down chevron rotated so it flows naturally in the list */}
                  </motion.span>
                )}
              </motion.div>
            ))}
          </motion.div>

          {/* Right: heading */}
          <div className="lg:pl-8">
            <SectionHeading
              eyebrow="How It Works"
              title="From prompt to perfect model"
              description="Every message flows through an intelligent pipeline that decides where it belongs. No manual model selection. No context loss."
              align="left"
            />

            {/* Mini stat row */}
            <motion.div
              variants={fadeUp}
              initial="hidden"
              whileInView="show"
              viewport={{ once: true, margin: "-60px" }}
              className="mt-8 grid grid-cols-3 gap-3"
            >
              {[
                { value: "<1s", label: "Routing latency" },
                { value: "97%", label: "Intent accuracy" },
                { value: "4+", label: "AI providers" },
              ].map((stat) => (
                <div key={stat.label} className="rounded-xl border border-[hsl(240,4%,18%)] bg-[hsl(240,5%,10%)] p-4 text-center">
                  <p className="text-xl font-semibold text-[hsl(193,58%,55%)]">{stat.value}</p>
                  <p className="mt-1 text-[11px] text-[hsl(240,5%,55%)]">{stat.label}</p>
                </div>
              ))}
            </motion.div>
          </div>
        </div>
      </div>
    </section>
  );
}
