"use client";

import { motion } from "framer-motion";
import { Cloud, Cpu, Sparkles, Zap } from "lucide-react";
import { fadeUp, stagger } from "@/components/landing/constants";
import { SectionHeading } from "@/components/landing/section-heading";

const PROVIDERS = [
  { name: "Gemini", vendor: "Google", icon: Sparkles, glowColor: "rgba(49,180,200,0.45)", desc: "Multimodal reasoning at scale." },
  { name: "Groq", vendor: "LPU Inference", icon: Zap, glowColor: "rgba(249,115,22,0.45)", desc: "Ultra low-latency responses." },
  { name: "Cloudflare", vendor: "Workers AI", icon: Cloud, glowColor: "rgba(49,180,200,0.35)", desc: "Edge-deployed open models." },
  { name: "Ollama", vendor: "Local Models", icon: Cpu, glowColor: "rgba(34,197,94,0.45)", desc: "Private, on-device inference." },
];

export function LandingProviders() {
  return (
    <section id="providers" className="scroll-mt-24 px-5 py-20 sm:px-8">
      <div className="mx-auto max-w-7xl">
        {/* ── Side-by-side: heading left, cards right ── */}
        <div className="grid items-start gap-12 lg:grid-cols-[1fr_1.6fr] lg:gap-16">
          {/* Left: label + heading */}
          <div className="lg:sticky lg:top-24">
            <SectionHeading
              eyebrow="Trusted Providers"
              title="One workspace, every leading model"
              description="Connect best-in-class providers side by side and let ThinkRoute pick the right one for each prompt."
              align="left"
            />
          </div>

          {/* Right: provider cards 2×2 */}
          <motion.div
            variants={stagger}
            initial="hidden"
            whileInView="show"
            viewport={{ once: true, margin: "-80px" }}
            className="grid grid-cols-1 gap-4 sm:grid-cols-2"
          >
            {PROVIDERS.map((provider) => (
              <motion.div
                key={provider.name}
                variants={fadeUp}
                whileHover={{ y: -4 }}
                className="group relative overflow-hidden rounded-xl border border-[hsl(240,4%,18%)] bg-[hsl(240,5%,10%)] p-6 transition-colors hover:border-[hsl(240,4%,25%)]"
              >
                <div
                  className="absolute -right-6 -top-6 h-24 w-24 rounded-full opacity-0 blur-2xl transition-opacity duration-300 group-hover:opacity-100"
                  style={{ background: provider.glowColor }}
                />
                <div className="relative">
                  <span className="flex h-11 w-11 items-center justify-center rounded-md border border-[hsl(240,4%,18%)] bg-[hsl(240,4%,14%)]">
                    <provider.icon className="h-5 w-5 text-[hsl(193,58%,48%)]" />
                  </span>
                  <h3 className="mt-4 text-base font-semibold text-white">{provider.name}</h3>
                  <p className="text-xs font-medium uppercase tracking-wide text-[hsl(240,5%,50%)]">{provider.vendor}</p>
                  <p className="mt-3 text-sm leading-6 text-[hsl(240,5%,64%)]">{provider.desc}</p>
                </div>
              </motion.div>
            ))}
          </motion.div>
        </div>
      </div>
    </section>
  );
}
