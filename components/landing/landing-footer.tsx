"use client";

import Link from "next/link";
import { BookOpen, BrainCircuit, Github, Mail } from "lucide-react";
import { CHAT_ROUTE, DOCS_URL, GITHUB_URL } from "@/components/landing/constants";

const APP_VERSION = "v0.1.0";

export function LandingFooter() {
  return (
    <footer className="border-t border-[hsl(240,4%,18%)] px-5 py-12 sm:px-8">
      <div className="mx-auto max-w-6xl">
        <div className="flex flex-col items-start justify-between gap-8 sm:flex-row">
          {/* Brand */}
          <div className="max-w-sm">
            <Link href="/" className="flex items-center gap-2.5">
              <span className="flex h-9 w-9 items-center justify-center rounded-md border border-[hsl(240,4%,18%)] bg-[hsl(240,5%,10%)]">
                <BrainCircuit className="h-4.5 w-4.5 text-[hsl(193,58%,48%)]" />
              </span>
              <span className="text-[15px] font-semibold tracking-tight text-white">
                ThinkRoute AI
              </span>
            </Link>
            <p className="mt-4 text-sm leading-6 text-[hsl(240,5%,64%)]">
              One Conversation. Every AI Model. Zero Context Loss. The
              intelligent AI orchestration platform.
            </p>
          </div>

          <div className="flex flex-wrap gap-x-12 gap-y-6">
            {/* Product links */}
            <div>
              <p className="text-xs font-semibold uppercase tracking-wide text-white">
                Product
              </p>
              <div className="mt-4 flex flex-col gap-3 text-sm">
                <Link
                  href={CHAT_ROUTE}
                  className="text-[hsl(240,5%,64%)] transition-colors hover:text-white"
                >
                  Start Chat
                </Link>
                <a
                  href="#features"
                  className="text-[hsl(240,5%,64%)] transition-colors hover:text-white"
                >
                  Features
                </a>
                <a
                  href="#architecture"
                  className="text-[hsl(240,5%,64%)] transition-colors hover:text-white"
                >
                  Architecture
                </a>
              </div>
            </div>
            {/* Resource links */}
            <div>
              <p className="text-xs font-semibold uppercase tracking-wide text-white">
                Resources
              </p>
              <div className="mt-4 flex flex-col gap-3 text-sm">
                <a
                  href={GITHUB_URL}
                  target="_blank"
                  rel="noreferrer"
                  className="flex items-center gap-2 text-[hsl(240,5%,64%)] transition-colors hover:text-white"
                >
                  <Github className="h-4 w-4" />
                  GitHub
                </a>
                <a
                  href={DOCS_URL}
                  target="_blank"
                  rel="noreferrer"
                  className="flex items-center gap-2 text-[hsl(240,5%,64%)] transition-colors hover:text-white"
                >
                  <BookOpen className="h-4 w-4" />
                  Documentation
                </a>
                <a
                  href="mailto:hello@thinknroute.ai"
                  className="flex items-center gap-2 text-[hsl(240,5%,64%)] transition-colors hover:text-white"
                >
                  <Mail className="h-4 w-4" />
                  Contact
                </a>
              </div>
            </div>
          </div>
        </div>

        {/* Bottom bar */}
        <div className="mt-10 flex flex-col items-center justify-between gap-3 border-t border-[hsl(240,4%,18%)] pt-6 text-xs text-[hsl(240,5%,50%)] sm:flex-row">
          <span>© {new Date().getFullYear()} ThinkRoute AI. All rights reserved.</span>
          <span className="rounded-full border border-[hsl(240,4%,18%)] bg-[hsl(240,5%,10%)] px-2.5 py-1 font-mono text-[hsl(193,58%,48%)]">
            {APP_VERSION}
          </span>
        </div>
      </div>
    </footer>
  );
}
