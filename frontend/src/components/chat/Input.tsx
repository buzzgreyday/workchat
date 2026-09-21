import { Send } from "lucide-react";

import { Button } from "../ui/button";
import { useControls } from "./ChatProvider";
import { useAutoResize } from "@/hooks/useAutoResize";
import { COMPOSER_PLACEHOLDER, NO_SESSION } from "@/lib/copy";

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
  } = useControls();

  const shut = loading || disabled;

  const boxRef = useAutoResize(input);

  return (
    <div className="border-line flex items-end gap-3 border-t p-gutter-sm">
      <textarea
        // A textarea rather than an input: a question worth asking a CV often
        // runs to two sentences, and there was no way to break a line — Enter
        // sent, and nothing else did anything.
        ref={boxRef}
        rows={1}
        // `text-body` is 16px and `text-meta` is 14px. The pair is not a style
        // choice: under 16px iOS zooms the page the moment the field takes
        // focus and does not zoom back out, which leaves the layout offset
        // behind the keyboard and looks exactly like the chat having broken.
        // Desktop keeps the 14px it always had.
        className="chat-field bg-panel-raised border-line text-ink placeholder:text-ink-muted max-h-composer-max min-h-control flex-1 resize-none rounded-control border px-4 py-3 text-body transition sm:text-meta"
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


      <Button
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
