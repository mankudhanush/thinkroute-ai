"use client";

import { useEffect, useRef } from "react";

export function useTextareaAutosize(value: string) {
  const ref = useRef<HTMLTextAreaElement | null>(null);

  useEffect(() => {
    const node = ref.current;

    if (!node) {
      return;
    }

    node.style.height = "0px";
    node.style.height = `${Math.min(node.scrollHeight, 180)}px`;
  }, [value]);

  return ref;
}
