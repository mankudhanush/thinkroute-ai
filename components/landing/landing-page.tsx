"use client";

import { useEffect } from "react";
import { LandingArchitecture } from "@/components/landing/landing-architecture";
import { LandingCta } from "@/components/landing/landing-cta";
import { LandingFeatures } from "@/components/landing/landing-features";
import { LandingFooter } from "@/components/landing/landing-footer";
import { LandingFuture } from "@/components/landing/landing-future";
import { LandingHero } from "@/components/landing/landing-hero";
import { LandingHowItWorks } from "@/components/landing/landing-how-it-works";
import { LandingNav } from "@/components/landing/landing-nav";
import { LandingProviders } from "@/components/landing/landing-providers";
import { LandingWhy } from "@/components/landing/landing-why";

/**
 * ThinkRoute marketing landing page ("/").
 *
 * Additive only — does not affect chat workspace, stores, routing engine, or backend.
 * "Start Chat" / "Get Started" navigate to the existing chat route (/app).
 *
 * globals.css sets `body { overflow: hidden }` for the app shell.
 * We temporarily enable page scrolling while the landing page is mounted
 * and restore it on unmount.
 */
export function LandingPage({ fontClassName = "" }: { fontClassName?: string }) {
  useEffect(() => {
    const body = document.body;
    const html = document.documentElement;
    const prev = {
      bodyOverflow: body.style.overflow,
      htmlOverflow: html.style.overflow,
      htmlScroll: html.style.scrollBehavior,
    };
    body.style.overflow = "auto";
    html.style.overflow = "auto";
    html.style.scrollBehavior = "smooth";
    return () => {
      body.style.overflow = prev.bodyOverflow;
      html.style.overflow = prev.htmlOverflow;
      html.style.scrollBehavior = prev.htmlScroll;
    };
  }, []);

  return (
    <div className={`min-h-dvh bg-[hsl(240,6%,7%)] text-white antialiased ${fontClassName}`}>
      <LandingNav />
      <main>
        <LandingHero />
        <LandingProviders />
        <LandingHowItWorks />
        <LandingFeatures />
        <LandingArchitecture />
        <LandingWhy />
        <LandingFuture />
        <LandingCta />
      </main>
      <LandingFooter />
    </div>
  );
}
