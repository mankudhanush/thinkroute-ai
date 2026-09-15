"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { motion } from "framer-motion";
import { ArrowRight, BrainCircuit, Github, Menu, X } from "lucide-react";
import { CHAT_ROUTE, GITHUB_URL } from "@/components/landing/constants";

const NAV_LINKS = [
  { label: "Features", href: "#features" },
  { label: "Architecture", href: "#architecture" },
  { label: "Providers", href: "#providers" },
  { label: "About", href: "#about" },
];

export function LandingNav() {
  const [scrolled, setScrolled] = useState(false);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    const handler = () => setScrolled(window.scrollY > 12);
    handler();
    window.addEventListener("scroll", handler, { passive: true });
    return () => window.removeEventListener("scroll", handler);
  }, []);

  return (
    <motion.header
      initial={{ opacity: 0, y: -16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5 }}
      className={`sticky top-0 z-50 border-b transition-colors duration-300 ${
        scrolled
          ? "border-[hsl(240,4%,18%)] bg-[hsl(240,6%,7%)]/90 backdrop-blur-xl"
          : "border-transparent bg-transparent"
      }`}
    >
      <nav className="mx-auto flex h-16 max-w-7xl items-center justify-between px-5 sm:px-8">
        {/* Logo — same icon+text as provider sidebar h1 */}
        <Link href="/" className="flex items-center gap-2.5">
          <span className="flex h-9 w-9 items-center justify-center rounded-md border border-[hsl(240,4%,18%)] bg-[hsl(240,5%,10%)]">
            <BrainCircuit className="h-4.5 w-4.5 text-[hsl(193,58%,48%)]" />
          </span>
          <span className="text-[15px] font-semibold tracking-tight text-white">
            ThinkRoute AI
          </span>
        </Link>

        {/* Desktop nav links */}
        <div className="hidden items-center gap-1 md:flex">
          {NAV_LINKS.map((link) => (
            <a
              key={link.href}
              href={link.href}
              className="rounded-md px-3 py-2 text-sm text-[hsl(240,5%,64%)] transition-colors hover:text-white"
            >
              {link.label}
            </a>
          ))}
          <a
            href={GITHUB_URL}
            target="_blank"
            rel="noreferrer"
            className="flex items-center gap-1.5 rounded-md px-3 py-2 text-sm text-[hsl(240,5%,64%)] transition-colors hover:text-white"
          >
            <Github className="h-4 w-4" />
            GitHub
          </a>
        </div>

        {/* CTA — matches chat app's accent teal */}
        <div className="hidden md:block">
          <Link
            href={CHAT_ROUTE}
            className="group inline-flex items-center gap-1.5 rounded-md border border-[hsl(193,58%,48%)]/50 bg-[hsl(193,58%,48%)]/10 px-4 py-2 text-sm font-medium text-[hsl(193,58%,48%)] transition-all hover:border-[hsl(193,58%,48%)] hover:bg-[hsl(193,58%,48%)]/20 hover:text-white"
          >
            Get Started
            <ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-0.5" />
          </Link>
        </div>

        {/* Mobile hamburger */}
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          className="inline-flex h-9 w-9 items-center justify-center rounded-md text-[hsl(240,5%,64%)] transition-colors hover:text-white md:hidden"
          aria-label="Toggle menu"
        >
          {open ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
        </button>
      </nav>

      {open ? (
        <motion.div
          initial={{ opacity: 0, height: 0 }}
          animate={{ opacity: 1, height: "auto" }}
          exit={{ opacity: 0, height: 0 }}
          className="overflow-hidden border-t border-[hsl(240,4%,18%)] bg-[hsl(240,6%,7%)]/95 backdrop-blur-xl md:hidden"
        >
          <div className="flex flex-col gap-1 px-5 py-4">
            {NAV_LINKS.map((link) => (
              <a
                key={link.href}
                href={link.href}
                onClick={() => setOpen(false)}
                className="rounded-md px-3 py-2.5 text-sm text-[hsl(240,5%,64%)] transition-colors hover:bg-white/5 hover:text-white"
              >
                {link.label}
              </a>
            ))}
            <a
              href={GITHUB_URL}
              target="_blank"
              rel="noreferrer"
              className="flex items-center gap-2 rounded-md px-3 py-2.5 text-sm text-[hsl(240,5%,64%)] transition-colors hover:bg-white/5 hover:text-white"
            >
              <Github className="h-4 w-4" />
              GitHub
            </a>
            <Link
              href={CHAT_ROUTE}
              onClick={() => setOpen(false)}
              className="mt-2 inline-flex items-center justify-center gap-1.5 rounded-md border border-[hsl(193,58%,48%)]/50 bg-[hsl(193,58%,48%)]/10 px-4 py-2.5 text-sm font-medium text-[hsl(193,58%,48%)]"
            >
              Get Started
              <ArrowRight className="h-4 w-4" />
            </Link>
          </div>
        </motion.div>
      ) : null}
    </motion.header>
  );
}
