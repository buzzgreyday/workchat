"use client";

import { useEffect, useState } from "react";

// Calm on purpose: a title that fidgets is a distraction, one that drifts is
// a detail. The two versions cross-fade slowly, then it rests.
const START_MS = 3000;
const FADE_MS = 1400;
const REST_MS = 7000;

/**
 * The title, with its two halves trading places now and then.
 *
 * "Workchat" and "chatWork" — WORKCHAT and CHATWORK, in Bebas — are stacked
 * in the same place, and one cross-fades into the other. The title never
 * goes dark, so nothing blinks: for a moment the letters blend, then it
 * settles on the other word. Nothing moves.
 *
 * A CSS transition between two opacities, so there is no animation state to
 * get stuck: whatever happens to the tab or the page, each layer is at its
 * resting opacity once the transition has run.
 *
 * Decoupled from everything else: it only needs the text, and splits it in
 * the middle. Screen readers get the text as written, once, and never the
 * swapped version. With reduced motion asked for, it is still.
 */
export default function RollingTitle({ text }: { text: string }) {
  const half = Math.floor(text.length / 2);
  const swappedText = text.slice(half) + text.slice(0, half);
  const [swapped, setSwapped] = useState(false);

  useEffect(() => {
    if (
      half === 0 ||
      window.matchMedia("(prefers-reduced-motion: reduce)").matches
    ) {
      return;
    }

    let timer: ReturnType<typeof setTimeout>;

    const switchOver = () => {
      setSwapped((current) => !current);
      timer = setTimeout(switchOver, FADE_MS + REST_MS);
    };

    timer = setTimeout(switchOver, START_MS);

    return () => clearTimeout(timer);
  }, [half]);

  const layer = (visible: boolean) =>
    `[grid-area:1/1] transition-opacity ease-in-out ${
      visible ? "opacity-100" : "opacity-0"
    }`;

  return (
    <>
      <span className="sr-only">{text}</span>
      <span aria-hidden="true" className="inline-grid">
        <span
          className={layer(!swapped)}
          style={{ transitionDuration: `${FADE_MS}ms` }}
        >
          {text}
        </span>
        <span
          className={layer(swapped)}
          style={{ transitionDuration: `${FADE_MS}ms` }}
        >
          {swappedText}
        </span>
      </span>
    </>
  );
}
