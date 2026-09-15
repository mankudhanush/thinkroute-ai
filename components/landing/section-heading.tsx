"use client";

import { motion } from "framer-motion";
import { fadeUp } from "@/components/landing/constants";

interface SectionHeadingProps {
  eyebrow: string;
  title: string;
  description?: string;
  /** "left" for side-by-side sections, "center" (default) for full-width */
  align?: "left" | "center";
}

export function SectionHeading({ eyebrow, title, description, align = "center" }: SectionHeadingProps) {
  const isLeft = align === "left";
  return (
    <motion.div
      variants={fadeUp}
      initial="hidden"
      whileInView="show"
      viewport={{ once: true, margin: "-80px" }}
      className={isLeft ? "" : "mx-auto max-w-2xl text-center"}
    >
      <span
        className={`inline-flex items-center gap-2 rounded-full border border-[hsl(240,4%,18%)] bg-[hsl(240,5%,10%)] px-3 py-1 text-xs font-medium tracking-wide text-[hsl(193,58%,55%)]`}
      >
        <span className="h-1.5 w-1.5 rounded-full bg-[hsl(193,58%,48%)]" />
        {eyebrow}
      </span>
      <h2
        className={`mt-4 text-3xl font-semibold tracking-tight text-white sm:text-4xl ${
          isLeft ? "" : "text-center"
        }`}
      >
        {title}
      </h2>
      {description ? (
        <p
          className={`mt-4 text-base leading-7 text-[hsl(240,5%,62%)] ${
            isLeft ? "max-w-md" : "mx-auto max-w-xl text-center"
          }`}
        >
          {description}
        </p>
      ) : null}
    </motion.div>
  );
}
