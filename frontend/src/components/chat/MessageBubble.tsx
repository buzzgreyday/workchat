import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { Message } from "@/types/chat";

import Progress from "./Progress";

interface MessageBubbleProps {
  message: Message;
}

export default function MessageBubble({
  message,
}: MessageBubbleProps) {
  const isUser = message.role === "user";

  return (
    <div
      className={`message ${isUser ? "message-user" : "message-bot"}`}
    >
      <div className="message-bubble chat-message">
        <BubbleContent message={message} />
      </div>
    </div>
  );
}

/**
 * What the bubble holds: the step a reply is waiting on, the typing dots
 * when there is no step to name, or the text once the first word arrives.
 */
function BubbleContent({ message }: MessageBubbleProps) {
  const isTyping =
    message.status === "streaming" && message.content === "";

  if (isTyping && message.progress) {
    return <Progress progress={message.progress} />;
  }

  if (isTyping) {
    return (
      <div
        className="typing-dots"
        aria-label="Generating a reply"
      >
        <span className="chat-typing-dot" />
        <span className="chat-typing-dot" />
        <span className="chat-typing-dot" />
      </div>
    );
  }

  return (
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
  );
}