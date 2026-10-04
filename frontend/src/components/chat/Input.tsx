import { useId } from "react";
import { Send } from "lucide-react";

import { Button } from "../ui/button";
import { useControls } from "./ChatProvider";
import { useAutoResize } from "@/hooks/useAutoResize";
import {
  COMPOSER_PLACEHOLDER,
  NO_SESSION,
  TRIAL_NOTICE,
  TRY_IT,
} from "@/lib/copy";
import { MAX_MESSAGE_CHARS } from "@/lib/limits";

// Where the trial button stands in for the composer: on offer, under way, or
// failed and worth another go. Used up and all-gone are dead ends the
// greeting explains, so the shut composer stays for those.
const OFFERS_TRIAL = new Set(["available", "starting", "failed"]);

export default function ChatInput() {
  const {
    input,
    loading,
    // No usable session — an unopened claim link, one already spent, or an
    // allowance that has run out. Separate from `loading` because it does not
    // clear on its own.
    disabled,
    // Why it is shut, shown in place of the prompt. Running out of questions
    // and never having had a session are both dead ends, but not the same one.
    disabledReason,
    setInput,
    sendMessage,
    trial,
    startTrial,
  } = useControls();

  const shut = loading || disabled;

  const boxRef = useAutoResize(input);
  const noticeId = useId();
  const lengthId = useId();

  // No link, and a trial on offer: the composer would only be a shut box, so
  // the way in goes where it was.
  if (OFFERS_TRIAL.has(trial)) {
    const starting = trial === "starting";

    return (
      <div className="flex flex-col items-stretch gap-2 p-gutter-sm">
        <Button
          onClick={() => startTrial()}
          disabled={starting}
          aria-describedby={noticeId}
          className="min-h-control rounded-control text-body shadow-sm"
        >
          {starting ? "Starting…" : TRY_IT}
        </Button>
        <p
          id={noticeId}
          className="text-center text-xs text-ink-muted"
        >
          {TRIAL_NOTICE}
        </p>
      </div>
    );
  }

  // Shown once something is typed, so an empty composer stays a quiet one.
  const counting = !shut && input.length > 0;
  const atLimit = input.length >= MAX_MESSAGE_CHARS;

  return (
    <div className="flex items-end gap-3 p-gutter-sm">
      <div className="relative flex min-w-0 flex-1">
        <textarea
          // A textarea rather than an input: a question worth asking a CV often
          // runs to two sentences, and there was no way to break a line — Enter
          // sent, and nothing else did anything.
          ref={boxRef}
          rows={1}
          // `text-body`, 16px, at every width. Not only a style choice: under
          // 16px iOS zooms the page the moment the field takes focus and does
          // not zoom back out, which leaves the layout offset behind the
          // keyboard and looks exactly like the chat having broken. Desktop used
          // to drop to 14px, which made the question look smaller than the same
          // words once they landed in a bubble; now what is typed matches.
          className={`chat-field bg-field border-field-line text-field-ink placeholder:text-field-placeholder max-h-composer-max min-h-control flex-1 resize-none rounded-control border px-4 py-3 text-body transition ${counting ? "pr-16" : ""}`}
          // Short on purpose, all three of them. A textarea soft-wraps, so a
          // placeholder wider than the box wraps to a second line inside a
          // one-row field and the composer scrolls before anything is typed.
          // The long version of why the chat is shut is already in the
          // transcript, where there is room for it.
          placeholder={
            disabled
              ? (disabledReason ?? NO_SESSION)
              : COMPOSER_PLACEHOLDER
          }
          aria-label="Your question"
          aria-describedby={counting ? lengthId : undefined}
          // The server refuses anything longer (MAX_MESSAGE_CHARS); stopping
          // here means nobody types a paragraph only to be told so.
          maxLength={MAX_MESSAGE_CHARS}
          value={input}
          disabled={shut}
          // Growing with the question is `useAutoResize`'s job now — keyed on the
          // value, so clearing on send shrinks the box back instead of leaving it
          // standing at the height of a question already asked.
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            // Enter still sends, because that is what a chat box does. Shift
            // holds it open for a second line.
            if (
              e.key === "Enter" &&
              !e.shiftKey
            ) {
              e.preventDefault();
              sendMessage();
            }
          }}
        />
        {counting && (
          <span
            id={lengthId}
            // Polite, and only at the limit: a count announced on every key
            // would drown out what is being typed.
            aria-live={atLimit ? "polite" : "off"}
            className={`pointer-events-none absolute right-3 bottom-2 text-xs tabular-nums ${atLimit ? "text-primary" : "text-field-placeholder"}`}
          >
            {input.length} / {MAX_MESSAGE_CHARS}
          </span>
        )}
      </div>

      <Button
        // Pressing the button must not take focus from the field. On a phone
        // that blur lowers the keyboard and brings the footer back, the
        // composer moves up under the finger, and the tap lands beside the
        // button — so the first tap did nothing and only a second one sent.
        // Keeping focus keeps the layout still, and leaves the keyboard up
        // for the next question. Keyboard activation is unaffected.
        onMouseDown={(e) => e.preventDefault()}
        onClick={() => sendMessage()}
        disabled={shut}
        aria-label="Send question"
        className="size-control shrink-0 rounded-control shadow-sm"
        >
        <Send size={18} />
      </Button>
    </div>
  );
}
