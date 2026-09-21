"use client";

import { useEffect } from "react";

/** The property the layout reads its height from. Consumed in globals.css. */
const PROPERTY = "--app-height";

/**
 * How far the pinch-zoom scale may drift from 1 before the visual viewport's
 * height stops meaning what this hook wants it to mean.
 */
const SCALE_EPSILON = 0.01;

/**
 * Keep the app exactly as tall as the part of the screen it can actually use.
 *
 * `interactiveWidget: "resizes-content"` in the layout's viewport export asks
 * the browser to shorten the *layout* viewport when the on-screen keyboard
 * opens, which is what keeps `dvh` honest. Chromium does it. iOS Safari
 * ignores it: the layout viewport stays full height and the *visual* viewport
 * shrinks instead. With `overflow: hidden` on `html` there is no document
 * scroll left to compensate, so on iOS the composer would sit behind the
 * keyboard with no way to reach it.
 *
 * So the height is measured rather than assumed. `visualViewport.height` is
 * the one number that is true on both engines.
 *
 * Published as a custom property rather than held in state, for two reasons:
 * this fires on every frame of a keyboard animation, and a re-render per frame
 * would drag the whole transcript through React; and a property write is not a
 * `setState`, so the hook stays clear of `react-hooks/set-state-in-effect`.
 */
export function useViewportHeight(): void {
  useEffect(() => {
    // Read inside the effect, never at module scope: this module is imported
    // during the server render, where there is no window.
    const viewport = window.visualViewport;

    // No Visual Viewport API. The stylesheet's `100dvh` fallback carries it,
    // which is exactly the behaviour that shipped before this hook existed.
    if (!viewport) {
      return;
    }

    const root = document.documentElement;

    const write = () => {
      const { height, scale } = viewport;

      // Zoomed in, `height` reports the slice of the page that fits on screen.
      // Honouring that would shrink the card to a sliver the moment someone
      // zoomed in to read an answer — the opposite of what zooming is for.
      // Hand back to the CSS fallback instead of guessing.
      if (
        height <= 0 ||
        Math.abs(scale - 1) > SCALE_EPSILON
      ) {
        root.style.removeProperty(PROPERTY);
        return;
      }

      const next = `${Math.round(height)}px`;

      // Compared before writing: Safari fires these in bursts through the
      // keyboard animation, and setting an identical value still invalidates
      // style on some engines.
      if (
        root.style.getPropertyValue(PROPERTY) !==
        next
      ) {
        root.style.setProperty(PROPERTY, next);
      }
    };

    write();

    viewport.addEventListener("resize", write);

    // Not because anything here reads `offsetTop` — the composer is
    // deliberately not pinned to it. For the height: iOS fires these two
    // inconsistently across versions, sometimes reporting a height through
    // `resize` before the keyboard has finished animating, sometimes only
    // firing `scroll` at all. Recomputing is idempotent, so a second chance
    // costs nothing.
    viewport.addEventListener("scroll", write);

    return () => {
      viewport.removeEventListener(
        "resize",
        write,
      );
      viewport.removeEventListener(
        "scroll",
        write,
      );

      // Removed rather than left behind: a stale height pinned to a document
      // nothing is watching any more is worse than the fallback it replaced.
      root.style.removeProperty(PROPERTY);
    };
  }, []);
}
