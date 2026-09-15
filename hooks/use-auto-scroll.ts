"use client";

import { useEffect, useRef } from "react";

/**
 * Auto-scrolls to the bottom of a container when dependencies change.
 * Accepts a primary dependency (e.g. message count) and an optional
 * secondary dependency (e.g. streaming text length) for smooth
 * streaming scroll.
 */
export function useAutoScroll<TPrimary, TSecondary = undefined>(
  primary: TPrimary,
  secondary?: TSecondary,
) {
  const ref = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    ref.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [primary, secondary]);

  return ref;
}
