"use client";

import { motion } from "framer-motion";
import { cn } from "@/lib/utils";

interface TypingIndicatorProps {
  className?: string;
}

export function TypingIndicator({ className }: TypingIndicatorProps) {
  return (
    <span className={cn("inline-flex items-center gap-1", className)}>
      {[0, 1, 2].map((dot) => (
        <motion.span
          animate={{ opacity: [0.35, 1, 0.35], y: [0, -2, 0] }}
          className="h-1.5 w-1.5 rounded-full bg-current"
          key={dot}
          transition={{
            duration: 0.9,
            repeat: Infinity,
            delay: dot * 0.12,
          }}
        />
      ))}
    </span>
  );
}
