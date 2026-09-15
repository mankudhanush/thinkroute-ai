"use client";

import { useCallback, useEffect, useRef, useState } from "react";

interface UseStreamingTextOptions {
  /** Speed in ms per character batch (lower = faster). Default 18 */
  speed?: number;
  /** Characters to reveal per tick. Default 2-4 (randomised) */
  chunkSize?: number;
  /** Whether streaming is enabled for this instance */
  enabled?: boolean;
}

interface UseStreamingTextReturn {
  /** The currently visible portion of the text */
  displayedText: string;
  /** Whether the animation is still running */
  isStreaming: boolean;
  /** Immediately reveal remaining text and stop */
  stop: () => void;
}

/**
 * Simulates token-by-token streaming for an already-complete text string.
 * The text is revealed in variable-sized chunks to mimic real LLM output.
 */
export function useStreamingText(
  fullText: string,
  options: UseStreamingTextOptions = {},
): UseStreamingTextReturn {
  const { speed = 18, enabled = true } = options;

  const [displayedLength, setDisplayedLength] = useState(enabled ? 0 : fullText.length);
  const [isStreaming, setIsStreaming] = useState(enabled && fullText.length > 0);
  const stoppedRef = useRef(false);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const currentLengthRef = useRef(enabled ? 0 : fullText.length);

  // Reset when fullText changes (new message)
  useEffect(() => {
    if (!enabled) {
      setDisplayedLength(fullText.length);
      setIsStreaming(false);
      return;
    }

    stoppedRef.current = false;
    currentLengthRef.current = 0;
    setDisplayedLength(0);
    setIsStreaming(fullText.length > 0);
  }, [fullText, enabled]);

  // The streaming animation loop
  useEffect(() => {
    if (!enabled || !isStreaming || stoppedRef.current) {
      return;
    }

    function tick() {
      if (stoppedRef.current) {
        return;
      }

      const current = currentLengthRef.current;
      const total = fullText.length;

      if (current >= total) {
        setIsStreaming(false);
        setDisplayedLength(total);
        return;
      }

      // Variable chunk size: larger chunks for whitespace/punctuation, smaller for words
      let chunkSize = 2 + Math.floor(Math.random() * 3); // 2-4 chars

      // Speed through whitespace and newlines
      const nextChars = fullText.slice(current, current + 12);
      if (/^[\s\n]+/.test(nextChars)) {
        chunkSize = Math.min(8, nextChars.match(/^[\s\n]+/)![0].length + 2);
      }

      // Speed through code block markers
      if (nextChars.startsWith("```")) {
        const endOfLine = fullText.indexOf("\n", current);
        chunkSize = endOfLine === -1 ? 6 : endOfLine - current + 1;
      }

      const newLength = Math.min(current + chunkSize, total);
      currentLengthRef.current = newLength;
      setDisplayedLength(newLength);

      if (newLength >= total) {
        setIsStreaming(false);
        return;
      }

      // Vary the interval slightly for a natural feel
      const jitter = speed + Math.floor(Math.random() * 12) - 4;
      timerRef.current = setTimeout(tick, Math.max(8, jitter));
    }

    timerRef.current = setTimeout(tick, 60); // small initial delay

    return () => {
      if (timerRef.current) {
        clearTimeout(timerRef.current);
      }
    };
  }, [fullText, isStreaming, enabled, speed]);

  const stop = useCallback(() => {
    stoppedRef.current = true;
    if (timerRef.current) {
      clearTimeout(timerRef.current);
      timerRef.current = null;
    }
    currentLengthRef.current = fullText.length;
    setDisplayedLength(fullText.length);
    setIsStreaming(false);
  }, [fullText]);

  return {
    displayedText: fullText.slice(0, displayedLength),
    isStreaming,
    stop,
  };
}
