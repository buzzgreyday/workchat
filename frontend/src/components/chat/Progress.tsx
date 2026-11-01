import { useEffect, useRef, useState } from "react";

import { PROGRESS } from "@/lib/copy";
import type { MessageProgress } from "@/types/chat";

// Long enough to read. Steps often finish in a few milliseconds, and a line
// replaced that quickly is a flicker rather than information.
const HOLD_MS = 400;

// Checked here, where both sides are known: a code with no words is a compile
// error rather than a blank bubble. `copy.ts` imports nothing, on purpose.
const WORDS: Record<MessageProgress, string> = PROGRESS;

/**
 * What a reply is waiting on, until its first word.
 *
 * Only the line is held back, never the reply: the first token unmounts this.
 * A step that arrives during a hold replaces any step already waiting, so a slow
 * reader sees the latest one rather than a queue running behind the work.
 *
 * The label is what a screen reader gets, one constant phrase, because reading
 * out each step would talk over the answer arriving.
 */
export default function Progress({
  progress,
}: {
  progress: MessageProgress;
}) {
  const [shown, setShown] = useState(progress);
  const shownAt = useRef(0);

  useEffect(() => {
    shownAt.current = Date.now();
  }, []);

  useEffect(() => {
    if (progress === shown) {
      return;
    }

    const wait = Math.max(
      0,
      shownAt.current + HOLD_MS - Date.now(),
    );

    const timer = setTimeout(() => {
      shownAt.current = Date.now();
      setShown(progress);
    }, wait);

    return () => clearTimeout(timer);
  }, [progress, shown]);

  return (
    <div
      className="chat-progress"
      aria-label="Generating a reply"
    >
      {WORDS[shown]}
    </div>
  );
}
