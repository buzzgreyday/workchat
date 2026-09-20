"use client";

import { useEffect, useRef } from "react";

// How far from the bottom still counts as "following along". Generous enough
// to survive the layout shift of a bubble growing by a line as it streams.
const NEAR_BOTTOM_PX = 120;

/**
 * Follow the conversation, unless the reader has gone looking.
 *
 * This used to scroll on every change to the dependency — which during a
 * streamed reply is every token. Scrolling up to re-read an earlier answer
 * while one was arriving dragged you straight back down again, once per token,
 * which made the transcript unreadable exactly when it was worth reading.
 *
 * So: only follow when already near the bottom. Scroll away and it leaves you
 * alone; scroll back and it resumes.
 */
export function useAutoScroll<T>(dependency: T) {
  const containerRef =
    useRef<HTMLDivElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const container = containerRef.current;

    if (!container) {
      return;
    }

    const distanceFromBottom =
      container.scrollHeight -
      container.scrollTop -
      container.clientHeight;

    if (distanceFromBottom > NEAR_BOTTOM_PX) {
      return;
    }

    bottomRef.current?.scrollIntoView({
      behavior: "smooth",
    });
  }, [dependency]);

  return { containerRef, bottomRef };
}
