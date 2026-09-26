import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Bot } from "lucide-react";

import { Message } from "@/types/chat";

interface MessageBubbleProps {
  message: Message;
}

export default function MessageBubble({
  message,
}: MessageBubbleProps) {
  const isUser = message.role === "user";
  const isStreaming = message.status === "streaming";
  const isTyping = isStreaming && message.content === "";

  return (
    <div
      className={`flex items-end gap-2 ${
        isUser ? "justify-end" : "justify-start"
      }`}
    >
      {!isUser && (
        <div
          className={`size-8 shrink-0 rounded-full ${
            isStreaming ? "chat-avatar-glow" : ""
          }`}
        >
          <div className="bg-accent text-on-accent flex size-8 items-center justify-center rounded-full">
            <Bot size={16} />
          </div>
        </div>
      )}

      <div
        className={`min-w-0 max-w-[var(--bubble-max-width)] wrap-anywhere rounded-bubble px-4 py-3 shadow-sm ${
          isUser
            ? "bg-accent text-ink rounded-br-sm"
            : "bg-panel-raised border-line text-ink rounded-bl-sm border"
        }`}
      >
        {isTyping ? (
          <div
            className="flex items-center gap-1 py-1"
            aria-label="Generating a reply"
          >
            <span className="chat-typing-dot bg-ink-muted h-1.5 w-1.5 rounded-full" />
            <span className="chat-typing-dot bg-ink-muted h-1.5 w-1.5 rounded-full" />
            <span className="chat-typing-dot bg-ink-muted h-1.5 w-1.5 rounded-full" />
          </div>
        ) : (
          <ReactMarkdown
            remarkPlugins={[remarkGfm]}
            components={{
              // An answer citing a repository or a profile should open beside
              // the chat, not replace it. Navigating away drops the access
              // token, which is held in memory on purpose.
              a: ({ children, ...props }) => (
                <a
                  {...props}
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  {children}
                </a>
              ),
            }}
          >
            {message.content}
          </ReactMarkdown>
        )}
      </div>
    </div>
  );
}