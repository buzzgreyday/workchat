import { Send } from "lucide-react";

import { Button } from "../ui/button";

interface ChatInputProps {
  value: string;
  loading: boolean;
  onChange: (value: string) => void;
  onSend: () => void;
}

export default function ChatInput({
  value,
  loading,
  onChange,
  onSend,
}: ChatInputProps) {
  return (
    <div className="flex gap-3 border-t border-[var(--chat-border)] p-4">
      <input
        className="chat-input h-11 flex-1 rounded-xl px-4 py-3 text-sm transition"
        placeholder="Ask me about work related stuff..."
        value={value}
        disabled={loading}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter") {
            onSend();
          }
        }}
      />


      <Button
        onClick={() => onSend()}
        disabled={loading}
        className="chat-accent-solid h-11 w-11 rounded-xl shadow-sm transition hover:brightness-110 disabled:opacity-50"
        >
        <Send size={18} />
      </Button>
    </div>
  );
}