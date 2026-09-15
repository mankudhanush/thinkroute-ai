"use client";

import Link from "next/link";
import { motion } from "framer-motion";
import { ArrowRight, BrainCircuit, Sparkles } from "lucide-react";
import { CHAT_ROUTE, fadeUp } from "@/components/landing/constants";

export function LandingCta() {
  return (
    <section className="px-5 py-20 sm:px-8">
      <motion.div
        variants={fadeUp}
        initial="hidden"
        whileInView="show"
        viewport={{ once: true, margin: "-80px" }}
        className="relative mx-auto max-w-7xl overflow-hidden rounded-2xl border border-[hsl(193,58%,48%)]/25 bg-[hsl(240,5%,10%)] px-8 py-14 sm:px-12 sm:py-16"
      >
        {/* Teal radial glow */}
        <div className="pointer-events-none absolute inset-0">
          <div
            className="absolute left-1/2 top-0 h-64 w-64 -translate-x-1/2 rounded-full blur-2xl"
            style={{ background: "radial-gradient(circle, rgba(49,180,200,0.2), transparent 62%)" }}
          />
          <div
            className="absolute inset-x-0 -top-px h-px"
            style={{ background: "linear-gradient(to right, transparent, hsl(193,58%,48%), transparent)" }}
          />
        </div>

        {/* ── Side-by-side: text left, CTA right ── */}
        <div className="relative flex flex-col items-start justify-between gap-8 sm:flex-row sm:items-center">
          {/* Left */}
          <div className="flex items-start gap-4">
            <span className="mt-0.5 flex h-10 w-10 shrink-0 items-center justify-center rounded-md border border-[hsl(193,58%,48%)]/40 bg-[hsl(193,58%,48%)]/10">
              <BrainCircuit className="h-5 w-5 text-[hsl(193,58%,55%)]" />
            </span>
            <div>
              <div className="mb-2 flex items-center gap-2">
                <span className="inline-flex items-center gap-1.5 rounded-full border border-[hsl(193,58%,48%)]/30 bg-[hsl(193,58%,48%)]/10 px-3 py-1 text-xs font-medium text-[hsl(193,58%,55%)]">
                  <Sparkles className="h-3 w-3" />
                  Ready to start?
                </span>
              </div>
              <h2 className="text-2xl font-semibold tracking-tight text-white sm:text-3xl">
                Experience intelligent AI routing
              </h2>
              <p className="mt-2 max-w-md text-sm leading-6 text-[hsl(240,5%,62%)]">
                One conversation. Every AI model. Zero context loss. Start routing your prompts in seconds.
              </p>
            </div>
          </div>

          {/* Right: CTA */}
          <div className="shrink-0">
            <Link
              href={CHAT_ROUTE}
              className="group inline-flex h-11 items-center gap-2 rounded-md border border-[hsl(193,58%,48%)]/60 bg-[hsl(193,58%,48%)]/15 px-7 text-sm font-semibold text-[hsl(193,58%,70%)] shadow-[0_4px_24px_-6px_rgba(49,180,200,0.4)] transition-all hover:border-[hsl(193,58%,48%)] hover:bg-[hsl(193,58%,48%)]/25 hover:text-white"
            >
              Start Chat
              <ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-0.5" />
            </Link>
          </div>
        </div>
      </motion.div>
    </section>
  );
}
