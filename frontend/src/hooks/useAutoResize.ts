"use client";

import { useLayoutEffect, useRef } from "react";

/**
 * A composer that grows with the question and shrinks back afterwards.
 *
 * This used to live inline in the textarea's `onChange`, which meant it ran on
 * every keystroke and on nothing else. Sending clears the value through state,
 * not through a change event, so the inline height set for a three-line
 * question survived the send: the box stayed tall and empty until something
 * else was typed into it.
 *
 * Keyed on the value instead, so every route to a new value resizes — typing,
 * clearing on send, and a draft restored from anywhere else later.
 *
 * `useLayoutEffect` rather than `useEffect`: the measure-and-set happens before
 * the browser paints, so the box never shows at the wrong height for a frame.
 */
export function useAutoResize(value: string) {
  const ref = useRef<HTMLTextAreaElement>(null);

  useLayoutEffect(() => {
    const box = ref.current;

    if (!box) {
      return;
    }

    // Reset first or the box can only ever get taller: `scrollHeight` counts
    // the height already forced onto the element, so measuring without this
    // measures the last answer rather than the current text.
    box.style.height = "auto";

    // `scrollHeight` is content plus padding and stops there, but Tailwind
    // sets `box-sizing: border-box`, so `height` has to cover the border as
    // well. Assigning one to the other loses exactly the border, and the field
    // scrolls by that much for ever after — two pixels, on a box that looks
    // perfectly fine. Measured rather than hardcoded, since the border is a
    // style decision that lives in CSS.
    const border =
      box.offsetHeight - box.clientHeight;

    box.style.height = `${box.scrollHeight + border}px`;
  }, [value]);

  return ref;
}
