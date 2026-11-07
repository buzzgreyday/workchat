"use client";

import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
} from "react";

import type { Message } from "@/types/chat";

// How close to the end still counts as "at the end": the button to go there
// is not shown for the last few pixels of a transcript.
const AT_END_PX = 24;

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
 * streams in. It grows down the page, under the reader's eyes, and once it
 * runs past the foot of the transcript a button offers the end, and the
 * reader decides when to go there.
 *
 * It used to follow the reply down, a line at a time, as long as the reader
 * was at the bottom. That kept the newest words in view and moved the
 * paragraph being read out from under the reader, once per token, for as long
 * as the answer took: what was meant to be read could not be. Following, and
 * stopping when the reader scrolled away, was the version before; this is the
 * one where nothing moves that the reader did not move.
 *
 * The room under a question is a spacer at the end of the transcript, sized so
 * the newest question can always reach the top: a short reply could not
 * otherwise scroll its question up there. It shrinks as the reply grows, to
 * nothing once the reply fills the view.
 *
 * The scroll is written to the transcript itself, never done with
 * `scrollIntoView()`. `scrollIntoView` is not scoped to the nearest scroller:
 * it scrolls *every* ancestor that can move, the document included — and
 * `overflow: hidden` on `html` only stops the user scrolling it, not script.
 * On a phone that walked the whole page up the screen and left it there,
 * where nobody could scroll it back. The question is scrolled to instantly:
 * its reply begins to arrive at once, and a smooth scroll would still be on
 * its way.
 */
export function useAutoScroll(messages: Message[]) {
  const containerRef =
    useRef<HTMLDivElement>(null);
  const spacerRef =
    useRef<HTMLDivElement>(null);

  // Whether the transcript is scrolled to its end — what the button to go
  // there is shown by. A ref as well as state: the resize observer reads it
  // without re-subscribing on every change.
  const [atEnd, setAtEnd] = useState(true);
  const atEndRef = useRef(true);

  // The question the transcript last scrolled for, so a new one is noticed
  // even when it lands in the same render as the reply bubble opened for it —
  // which it does, so "is the last message the user's?" is never true here.
  const askedRef = useRef<string | null>(null);

  /** Re-reads whether the transcript is at its end. */
  const measure = useCallback(() => {
    const container = containerRef.current;

    if (!container) {
      return;
    }

    const end =
      container.scrollHeight -
        container.scrollTop -
        container.clientHeight <=
      AT_END_PX;

    atEndRef.current = end;
    setAtEnd(end);
  }, []);

  /**
   * Sizes the spacer so the newest question can be scrolled to the top,
   * and returns where the transcript scrolls to put it there.
   */
  const fit = useCallback((): number | null => {
    const container = containerRef.current;
    const spacer = spacerRef.current;

    if (!container || !spacer) {
      return null;
    }

    const questions =
      container.querySelectorAll<HTMLElement>(
        ".message-user",
      );
    const question = questions[questions.length - 1];

    if (!question) {
      spacer.style.height = "0px";

      return null;
    }

    const style = getComputedStyle(container);
    const padTop = parseFloat(style.paddingTop);
    const padBottom = parseFloat(style.paddingBottom);

    // Where the question is to be: its top on the transcript's own top
    // padding, as the first message sits when there is nothing above it.
    const target = question.offsetTop - padTop;

    // How far the transcript can scroll with no spacer — its content ends
    // where the spacer begins — and so how much the spacer has to add.
    const room =
      target +
      container.clientHeight -
      (spacer.offsetTop + padBottom);

    spacer.style.height = `${Math.max(0, room)}px`;

    return target;
  }, []);

  useEffect(() => {
    const container = containerRef.current;

    if (!container) {
      return;
    }

    // The transcript changes height without its content changing when the
    // on-screen keyboard opens and the card shrinks to fit above it. The room
    // under the question is re-sized to the new height, and a reader who was
    // at the end stays there rather than a keyboard's height above it.
    const observer = new ResizeObserver(() => {
      fit();

      if (atEndRef.current) {
        container.scrollTop =
          container.scrollHeight;
      }

      measure();
    });

    container.addEventListener(
      "scroll",
      measure,
      { passive: true },
    );
    observer.observe(container);

    return () => {
      container.removeEventListener(
        "scroll",
        measure,
      );
      observer.disconnect();
    };
  }, [fit, measure]);

  // A layout effect so the room and the scroll are settled before the browser
  // paints: as a plain effect, a new question was drawn once where it landed
  // and then moved.
  useLayoutEffect(() => {
    const container = containerRef.current;

    if (!container) {
      return;
    }

    const target = fit();

    const asked = lastAskedId(messages);
    const justAsked =
      asked !== askedRef.current;

    askedRef.current = asked;

    if (justAsked && target !== null) {
      container.scrollTop = target;
    }

    measure();
  }, [messages, fit, measure]);

  /** To the end, smoothly unless the reader has asked for less motion. */
  const toEnd = useCallback(() => {
    const container = containerRef.current;

    if (!container) {
      return;
    }

    const still = window.matchMedia(
      "(prefers-reduced-motion: reduce)",
    ).matches;

    container.scrollTo({
      top: container.scrollHeight,
      behavior: still ? "auto" : "smooth",
    });
  }, []);

  return { containerRef, spacerRef, atEnd, toEnd };
}
