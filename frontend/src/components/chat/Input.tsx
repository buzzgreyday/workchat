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
    <div className="flex gap-3 border-t border-[var(--chat-border)] p-4">
      <input
        className="chat-input h-11 flex-1 rounded-xl px-4 py-3 text-sm transition"
        placeholder={
          disabled
            ? (disabledReason ??
              "This link can't start a session")
            : "Ask me about work related stuff..."
        }
        value={value}
        disabled={shut}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter") {
            onSend();
          }
        }}
      />


      <Button
        onClick={() => onSend()}
        disabled={shut}
        className="chat-accent-solid h-11 w-11 rounded-xl shadow-sm transition hover:brightness-110 disabled:opacity-50"
        >
        <Send size={18} />
      </Button>
    </div>
  );
}