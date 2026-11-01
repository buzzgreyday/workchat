import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

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
      className={`message ${isUser ? "message-user" : "message-bot"}`}
    >
      <div
        className="message-bubble chat-message"
      >
        {isTyping ? (
          <div
            className="typing-dots"
            aria-label="Generating a reply"
          >
            <span className="chat-typing-dot" />
            <span className="chat-typing-dot" />
            <span className="chat-typing-dot" />
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