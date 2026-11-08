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
 * Show each new question at the top of the transcript, and then hold still.
 *
 * The rest is CSS (styles/chat.css): a browser does not move the view when
 * content grows below it, so the reply streams in under the question with
 * nothing moving; the room under the question is a minimum height on the
 * newest reply; and the button to the end shows and hides itself from the
 * scroll position. What CSS cannot do is notice a question was just asked,
 * and go to the end on a press without a link, which would put a `#` in the
 * host page's address. That is this.
 *
 * It used to follow a reply down a line at a time, and the paragraph being
 * read moved out from under the reader once per token.
 *
 * The scroll is written to the transcript itself, never done with
 * `scrollIntoView()`, which scrolls *every* ancestor that can move, the
 * document included: on a phone that walked the whole page up the screen and
 * left it there. To the question it is instant — its reply begins to arrive
 * at once — and to the end, as the transcript's `scroll-behavior` says.
 */
export function useScrollToQuestion(messages: Message[]) {
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
