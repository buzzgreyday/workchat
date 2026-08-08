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
          className={`h-8 w-8 shrink-0 rounded-full ${
            isStreaming ? "chat-avatar-glow" : ""
          }`}
        >
          <div className="chat-avatar flex h-8 w-8 items-center justify-center rounded-full">
            <Bot size={16} />
          </div>
        </div>
      )}

      <div
        className={`max-w-[80%] rounded-2xl px-4 py-3 shadow-sm ${
          isUser
            ? "chat-bubble-user rounded-br-sm"
            : "chat-bubble-assistant rounded-bl-sm"
        }`}
      >
        {isTyping ? (
          <div className="flex items-center gap-1 py-1">
            <span className="chat-typing-dot h-1.5 w-1.5 rounded-full bg-slate-400" />
            <span className="chat-typing-dot h-1.5 w-1.5 rounded-full bg-slate-400" />
            <span className="chat-typing-dot h-1.5 w-1.5 rounded-full bg-slate-400" />
          </div>
        ) : (
          <ReactMarkdown remarkPlugins={[remarkGfm]}>
            {message.content}
          </ReactMarkdown>
        )}
      </div>
    </div>
  );
}