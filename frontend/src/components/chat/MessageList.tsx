import { Message } from "@/types/chat";
import MessageBubble from "./MessageBubble";
import { useAutoScroll } from "@/hooks/useAutoScroll";


interface MessageListProps {
  messages: Message[];
}

// Rendering each message, no fetch, jwt, etc.
export default function MessageList({
  messages,
}: MessageListProps) {
  const bottomRef = useAutoScroll(messages);

  return (
    <div className="flex-1 overflow-y-auto p-6 space-y-4">
      {messages.map((message) => (
        <MessageBubble
          key={message.id}
          message={message}
        />
        )
        )
      }
    <div ref={bottomRef} />
  </div>
);
}