"use client";

import { useEffect, useLayoutEffect, useRef, useState } from "react";

// Quiet on purpose: a title that fidgets is a distraction, one that drifts is
// a detail. The word blinks out, its halves trade places while it is gone,
// and it comes back; then it rests.
const START_MS = 2500;
const OUT_MS = 420;
const IN_MS = 250;
const REST_MS = 6000;

/**
 * The title, with its two halves trading places now and then.
 *
 * "Workchat" becomes "chatWork" and back — WORKCHAT, CHATWORK, WORKCHAT, in
 * Bebas. The whole word blinks out, dimming in two quick flickers to nothing
 * the way a sign goes, the halves swap while nothing is showing, and the
 * word fades back in where it was. Nothing moves, so it never takes more
 * attention than a glance.
 *
 * One switch at a time, each starting only once the last has finished: in a
 * background tab, where timers run but animations wait, switches cannot pile
 * up.
 *
 * Decoupled from everything else: it only needs the text, and splits it in
 * the middle. Screen readers get the text as written, once, and never the
 * swapped version. With reduced motion asked for, it is still.
 */
export default function RollingTitle({ text }: { text: string }) {
  const half = Math.floor(text.length / 2);
  const [swapped, setSwapped] = useState(false);

  const word = useRef<HTMLSpanElement>(null);
  const appearing = useRef(false);

  useEffect(() => {
    const el = word.current;

    if (
      !el ||
      half === 0 ||
      window.matchMedia("(prefers-reduced-motion: reduce)").matches
    ) {
      return;
    }

    let live = true;
    let timer: ReturnType<typeof setTimeout>;

    const step = () => {
      // Blink out: dim, recover part of the way, dim further, gone.
      el.animate(
        [
          { opacity: 1 },
          { opacity: 0.25, offset: 0.2 },
          { opacity: 0.8, offset: 0.35 },
          { opacity: 0.1, offset: 0.6 },
          { opacity: 0.45, offset: 0.75 },
          { opacity: 0 },
        ],
        { duration: OUT_MS, easing: "linear", fill: "forwards" },
      ).finished.then(
        () => {
          if (!live) {
            return;
          }

          // Swap while nothing is showing; the layout effect brings it back.
          appearing.current = true;
          setSwapped((current) => !current);
          timer = setTimeout(step, IN_MS + REST_MS);
        },
        () => {},
      );
    };

    timer = setTimeout(step, START_MS);

    return () => {
      live = false;
      clearTimeout(timer);
      // A blink cut short (a reload, an unmount) must not leave the word
      // held at its invisible end state.
      el.getAnimations().forEach((anim) => anim.cancel());
    };
  }, [half]);

  // The swapped word is in the DOM, not yet painted, and still hidden by the
  // blink's held end state: replace that with a short fade in.
  useLayoutEffect(() => {
    const el = word.current;

    if (!appearing.current || !el) {
      return;
    }

    appearing.current = false;
    el.getAnimations().forEach((anim) => anim.cancel());
    el.animate([{ opacity: 0 }, { opacity: 1 }], {
      duration: IN_MS,
      easing: "ease-out",
    });
  }, [swapped]);

  return (
    <>
      <span className="sr-only">{text}</span>
      <span ref={word} aria-hidden="true" className="inline-block">
        {swapped ? text.slice(half) + text.slice(0, half) : text}
      </span>
    </>
  );
}
