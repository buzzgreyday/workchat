"use client";

import {
  useCallback,
  useLayoutEffect,
  useRef,
} from "react";

import type { Message } from "@/types/chat";

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
 * Show each question at the top of the transcript, and then hold still.
 *
 * Asking a question scrolls once: the question to the top, with the room
 * under it for the reply to arrive into. Then nothing moves while the reply
 * streams in. It grows down the page, under the reader's eyes; once it runs
 * past the foot of the transcript a button offers the end, and the reader
 * decides when to go there.
 *
 * Almost all of that is CSS (styles/chat.css), and this is what is left. A
 * browser does not move the view when content grows below it, so holding
 * still needs nothing at all. The room under the question is a minimum
 * height on the newest reply, in the transcript's own container units. The
 * button shows and hides itself from the scroll position, a scroll-driven
 * animation. What CSS cannot do is notice that a question was just asked, and
 * scroll to it; and it cannot be told to go to the end on a press without a
 * link, which would put a `#` in the host page's address.
 *
 * It used to follow the reply down, a line at a time, as long as the reader
 * was at the bottom: the paragraph being read moved out from under the
 * reader once per token. A first version of this one measured the room and
 * the end in script, on every token and every resize, and was replaced by the
 * CSS that does the same without it.
 *
 * The scroll is written to the transcript itself, never done with
 * `scrollIntoView()`. `scrollIntoView` is not scoped to the nearest scroller:
 * it scrolls *every* ancestor that can move, the document included — and
 * `overflow: hidden` on `html` only stops the user scrolling it, not script.
 * On a phone that walked the whole page up the screen and left it there,
 * where nobody could scroll it back. To the question it is instant — its
 * reply begins to arrive at once — and to the end, as the transcript's
 * `scroll-behavior` says: smooth, unless the reader asks for less motion.
 */
export function useAutoScroll(messages: Message[]) {
  const containerRef =
    useRef<HTMLDivElement>(null);

  // The question the transcript last scrolled for, so a new one is noticed
  // even when it lands in the same render as the reply bubble opened for it —
  // which it does, so "is the last message the user's?" is never true here.
  const askedRef = useRef<string | null>(null);

  // A layout effect so the question is in place before the browser paints:
  // as a plain effect it was drawn once where it landed, and then moved.
  useLayoutEffect(() => {
    const container = containerRef.current;
    const asked = lastAskedId(messages);

    if (!container || asked === askedRef.current) {
      return;
    }

    askedRef.current = asked;

    const questions =
      container.querySelectorAll<HTMLElement>(
        ".message-user",
      );
    const question = questions[questions.length - 1];

    if (!question) {
      return;
    }

    // Its top on the transcript's own top padding, where the first message
    // sits when there is nothing above it. Measured from the transcript,
    // which is positioned for it.
    container.scrollTo({
      top:
        question.offsetTop -
        parseFloat(getComputedStyle(container).paddingTop),
      behavior: "instant",
    });
  }, [messages]);

  const toEnd = useCallback(() => {
    const container = containerRef.current;

    container?.scrollTo({ top: container.scrollHeight });
  }, []);

  return { containerRef, toEnd };
}
