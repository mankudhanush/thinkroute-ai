"use client";

import Link from "next/link";
import { motion, type Variants } from "framer-motion";
import { ArrowRight, BrainCircuit, Sparkles, Waypoints } from "lucide-react";
import { CHAT_ROUTE } from "@/components/landing/constants";
import { HeroPreview } from "@/components/landing/hero-preview";

const NODES = [
  { top: "22%", left: "6%", size: 7, delay: 0 },
  { top: "32%", left: "91%", size: 6, delay: 0.6 },
  { top: "60%", left: "4%", size: 5, delay: 1.1 },
  { top: "14%", left: "68%", size: 4, delay: 0.9 },
];

const container: Variants = {
  hidden: {},
  show: { transition: { staggerChildren: 0.09, delayChildren: 0.05 } },
};
const item: Variants = {
  hidden: { opacity: 0, y: 18 },
  show: { opacity: 1, y: 0, transition: { duration: 0.55, ease: [0.21, 0.47, 0.32, 0.98] } },
};

const TRUST = ["Gemini", "Groq", "Cloudflare Workers AI", "Ollama"];

export function LandingHero() {
  return (
    <section className="relative overflow-hidden px-5 pb-20 pt-20 sm:px-8 sm:pt-24">
      {/* Ambient teal glow */}
      <div className="pointer-events-none absolute inset-0 -z-10">
        <motion.div
          animate={{ opacity: [0.3, 0.55, 0.3] }}
          transition={{ duration: 8, repeat: Infinity, ease: "easeInOut" }}
          className="absolute left-1/2 top-[-10%] h-[500px] w-[800px] -translate-x-1/2 rounded-full blur-3xl"
          style={{ background: "radial-gradient(ellipse at center, rgba(49,180,200,0.16), transparent 60%)" }}
        />
        <div className="absolute inset-0 bg-[linear-gradient(rgba(255,255,255,0.016)_1px,transparent_1px),linear-gradient(90deg,rgba(255,255,255,0.016)_1px,transparent_1px)] bg-[size:60px_60px] [mask-image:radial-gradient(ellipse_60%_50%_at_50%_0%,black,transparent)]" />
      </div>

      {/* Floating nodes */}
      <div className="pointer-events-none absolute inset-0 -z-10 hidden sm:block">
        {NODES.map((node, i) => (
          <motion.span
            key={i}
            animate={{ opacity: [0.25, 0.8, 0.25], y: [0, -10, 0] }}
            transition={{ duration: 5, repeat: Infinity, ease: "easeInOut", delay: node.delay }}
            style={{ top: node.top, left: node.left, width: node.size, height: node.size }}
            className="absolute rounded-full bg-[hsl(193,58%,48%)] shadow-[0_0_12px_2px_rgba(49,180,200,0.55)]"
          />
        ))}
      </div>

      {/* ── Side-by-side: text left, preview right ── */}
      <div className="mx-auto max-w-7xl">
        <div className="grid items-center gap-12 lg:grid-cols-2 lg:gap-16">
          {/* Left: headline + CTA */}
          <motion.div variants={container} initial="hidden" animate="show">
            <motion.div variants={item} className="mb-5">
              <span className="inline-flex items-center gap-2 rounded-full border border-[hsl(240,4%,18%)] bg-[hsl(240,5%,10%)] px-3.5 py-1.5 text-xs font-medium text-[hsl(193,58%,55%)]">
                <Sparkles className="h-3.5 w-3.5" />
                Intelligent AI orchestration
              </span>
            </motion.div>

            <motion.h1
              variants={item}
              className="text-5xl font-semibold leading-[1.05] tracking-[-0.02em] text-white sm:text-6xl"
            >
              Think Smarter.{" "}
              <span
                className="bg-clip-text text-transparent"
                style={{ backgroundImage: "linear-gradient(90deg, hsl(193,58%,55%), hsl(193,58%,72%), hsl(193,58%,55%))" }}
              >
                Route Better.
              </span>
            </motion.h1>

            <motion.p
              variants={item}
              className="mt-6 max-w-lg text-base leading-7 text-[hsl(240,5%,64%)]"
            >
              <span className="font-medium text-white/90">One conversation. Every AI model. Zero context loss.</span>{" "}
              ThinkRoute automatically selects the best model for every task — preserving context, reducing cost, and maximizing performance.
            </motion.p>

            <motion.div variants={item} className="mt-8 flex flex-wrap items-center gap-3">
              <Link
                href={CHAT_ROUTE}
                className="group inline-flex h-11 items-center gap-2 rounded-md border border-[hsl(193,58%,48%)]/60 bg-[hsl(193,58%,48%)]/15 px-6 text-sm font-semibold text-[hsl(193,58%,70%)] shadow-[0_4px_24px_-6px_rgba(49,180,200,0.4)] transition-all hover:border-[hsl(193,58%,48%)] hover:bg-[hsl(193,58%,48%)]/25 hover:text-white"
              >
                Start Chat
                <ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-0.5" />
              </Link>
              <a
                href="#architecture"
                className="inline-flex h-11 items-center gap-2 rounded-md border border-[hsl(240,4%,18%)] bg-[hsl(240,5%,10%)] px-6 text-sm font-medium text-[hsl(240,5%,64%)] transition-colors hover:bg-[hsl(240,4%,14%)] hover:text-white"
              >
                <Waypoints className="h-4 w-4" />
                Architecture
              </a>
            </motion.div>

            <motion.div variants={item} className="mt-8">
              <p className="text-[11px] font-medium uppercase tracking-[0.16em] text-[hsl(240,5%,42%)]">
                Routes across leading providers
              </p>
              <div className="mt-2.5 flex flex-wrap gap-x-5 gap-y-1.5 text-sm font-medium text-[hsl(240,5%,60%)]">
                {TRUST.map((t) => (
                  <span key={t} className="transition-colors hover:text-white">{t}</span>
                ))}
              </div>
            </motion.div>
          </motion.div>

          {/* Right: HeroPreview */}
          <motion.div
            initial={{ opacity: 0, x: 24 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.7, delay: 0.2, ease: [0.21, 0.47, 0.32, 0.98] }}
          >
            <HeroPreview inline />
          </motion.div>
        </div>
      </div>
    </section>
  );
}
