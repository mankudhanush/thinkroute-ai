import type { Variants } from "framer-motion";

/**
 * Landing-page-only constants and shared motion variants.
 * Color palette mirrors the chat app's CSS variable system:
 *   --background: 240 6% 7%  → #101013
 *   --card:       240 5% 10% → #181820
 *   --secondary:  240 4% 14% → #202028
 *   --accent:     193 58% 48% → #31b4c8 (teal)
 *   --border:     240 4% 18% → rgba(255,255,255,0.08)
 */

export const CHAT_ROUTE = "/app";
export const GITHUB_URL = "https://github.com";
export const DOCS_URL = "https://github.com";

// Palette aligned to the existing CSS variable design system.
export const COLORS = {
  background: "hsl(240,6%,7%)",      // --background
  card: "hsl(240,5%,10%)",           // --card
  secondary: "hsl(240,4%,14%)",      // --secondary
  accent: "hsl(193,58%,48%)",        // --accent  (teal)
  accentDim: "rgba(49,180,200,0.12)",
  accentGlow: "rgba(49,180,200,0.35)",
  success: "#22C55E",
  textPrimary: "hsl(0,0%,96%)",      // --foreground
  textSecondary: "hsl(240,5%,64%)",  // --muted-foreground
  border: "hsl(240,4%,18%)",         // --border
  borderSubtle: "rgba(255,255,255,0.06)",
} as const;

export const fadeUp: Variants = {
  hidden: { opacity: 0, y: 18 },
  show: {
    opacity: 1,
    y: 0,
    transition: { duration: 0.5, ease: [0.21, 0.47, 0.32, 0.98] },
  },
};

export const stagger: Variants = {
  hidden: {},
  show: {
    transition: { staggerChildren: 0.08 },
  },
};
