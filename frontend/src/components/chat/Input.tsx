import { Send } from "lucide-react";

import { Button } from "../ui/button";

interface ChatInputProps {
  value: string;
  loading: boolean;
  // No usable session — an unopened claim link, one already spent, or an
  // allowance that has run out. Separate from `loading` because it does not
  // clear on its own.
  disabled?: boolean;
  // Why it is shut, shown in place of the prompt. Running out of questions and
  // never having had a session are both dead ends, but not the same one.
  disabledReason?: string | null;
  onChange: (value: string) => void;
  onSend: () => void;
}

export default function ChatInput({
  value,
  loading,
  disabled = false,
  disabledReason,
  onChange,
  onSend,
}: ChatInputProps) {
  const shut = loading || disabled;

  return (
    <div className="flex items-end gap-3 border-t border-[var(--chat-border)] p-4">
      <textarea
        // A textarea rather than an input: a question worth asking a CV often
        // runs to two sentences, and there was no way to break a line — Enter
        // sent, and nothing else did anything.
        rows={1}
        className="chat-input max-h-32 min-h-11 flex-1 resize-none rounded-xl px-4 py-3 text-sm transition"
        placeholder={
          disabled
            ? (disabledReason ??
              "This link can't start a session")
            : "Ask me about work related stuff..."
        }
        aria-label="Your question"
        value={value}
        disabled={shut}
        onChange={(e) => {
          onChange(e.target.value);

          // Grow with the question, up to the max-height above, after which it
          // scrolls. Reset first or the box can only ever get taller.
          const box = e.currentTarget;
          box.style.height = "auto";
          box.style.height = `${box.scrollHeight}px`;
        }}
        onKeyDown={(e) => {
          // Enter still sends, because that is what a chat box does. Shift
          // holds it open for a second line.
          if (
            e.key === "Enter" &&
            !e.shiftKey
          ) {
            e.preventDefault();
            onSend();
          }
        }}
      />


      <Button
        onClick={() => onSend()}
        disabled={shut}
        aria-label="Send question"
        className="chat-accent-solid h-11 w-11 shrink-0 rounded-xl shadow-sm transition hover:brightness-110 disabled:opacity-50"
        >
        <Send size={18} />
      </Button>
    </div>
  );
}
