"use client";

import {
  useEffect,
  useLayoutEffect,
  useRef,
} from "react";

import type { Message } from "@/types/chat";

// How far from the bottom still counts as "following along". Generous enough
// to survive the layout shift of a bubble growing by a line as it streams.
const NEAR_BOTTOM_PX = 120;

/** The newest question in the transcript, or null before the first one. */
function lastAskedId(
  messages: Message[],
): string | null {
  for (
    let index = messages.length - 1;
    index >= 0;
    index -= 1
  ) {
    const message = messages[index];

    if (message?.role === "user") {
      return message.id;
    }
  }

  return null;
}

/**
 * Follow the conversation, unless the reader has gone looking.
 *
 * This used to scroll on every change to the transcript — which during a
 * streamed reply is every token. Scrolling up to re-read an earlier answer
 * while one was arriving dragged you straight back down again, once per token,
 * which made the transcript unreadable exactly when it was worth reading.
 *
 * So: follow only while the reader is at the bottom. Scroll away and it leaves
 * you alone; scroll back and it resumes. With one exception — asking a
 * question always comes back down. Whoever just pressed send is looking for
 * their question and the answer to it, not for the paragraph they had
 * scrolled up to, and leaving them there sent both below the fold.
 *
 * "At the bottom" is remembered from the reader's last scroll, not measured
 * after the new content lands. Measured afterwards, a chunk taller than
 * NEAR_BOTTOM_PX — a restored transcript, a model that sends a paragraph at a
 * time — reads as "scrolled away" and following stops on its own, with nobody
 * having touched anything.
 *
 * The scroll is written to the transcript itself, never done with
 * `scrollIntoView()` on a sentinel at the end of it. `scrollIntoView` is not
 * scoped to the nearest scroller: it scrolls *every* ancestor that can move,
 * the document included — and `overflow: hidden` on `html` only stops the
 * user scrolling it, not script. Once per token, that walked the whole page
 * up the screen on a phone and left it there, where nobody could scroll it
 * back. Instant rather than smooth: a smooth scroll restarted on every token
 * lags behind the text and never settles.
 */
export function useAutoScroll(messages: Message[]) {
  const containerRef =
    useRef<HTMLDivElement>(null);

  // Whether the reader was at the bottom as of their last scroll.
  const pinnedRef = useRef(true);

  // The question the transcript last scrolled for, so a new one is noticed
  // even when it lands in the same render as the reply bubble opened for it —
  // which it does, so "is the last message the user's?" is never true here.
  const askedRef = useRef<string | null>(null);

  useEffect(() => {
    const container = containerRef.current;

    if (!container) {
      return;
    }

    const remember = () => {
      pinnedRef.current =
        container.scrollHeight -
          container.scrollTop -
          container.clientHeight <=
        NEAR_BOTTOM_PX;
    };

    // The transcript changes height without its content changing when the
    // on-screen keyboard opens and the card shrinks to fit above it. A reader
    // who was following should still be looking at the newest line, not at
    // whatever was a keyboard's height above it.
    const observer = new ResizeObserver(() => {
      if (pinnedRef.current) {
        container.scrollTop =
          container.scrollHeight;
      }
    });

    container.addEventListener(
      "scroll",
      remember,
      { passive: true },
    );
    observer.observe(container);

    return () => {
      container.removeEventListener(
        "scroll",
        remember,
      );
      observer.disconnect();
    };
  }, []);

  // A layout effect so the scroll lands before the browser paints. As a plain
  // effect each token was drawn once below the fold and then scrolled up to,
  // which on a slow phone is a visible stutter per token.
  useLayoutEffect(() => {
    const container = containerRef.current;

    if (!container) {
      return;
    }

    const asked = lastAskedId(messages);
    const justAsked =
      asked !== askedRef.current;

    askedRef.current = asked;

    if (!justAsked && !pinnedRef.current) {
      return;
    }

    container.scrollTop =
      container.scrollHeight;
    pinnedRef.current = true;
  }, [messages]);

  return { containerRef };
}
