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
  const { containerRef, bottomRef } =
    useAutoScroll(messages);

  const awaitingReply =
    messages.at(-1)?.status === "streaming";

  return (
    <div
      ref={containerRef}
      // `log` rather than a live region around the text: a reply arrives a
      // token at a time, and announcing each one would read the answer out
      // character by character. The status line below says what is happening
      // instead, which is the part a screen reader actually needs.
      role="log"
      aria-label="Conversation"
      className="flex-1 overflow-y-auto p-6 space-y-4"
    >
      {messages.map((message) => (
        <MessageBubble
          key={message.id}
          message={message}
        />
        )
        )
      }

      <p role="status" className="sr-only">
        {awaitingReply
          ? "Generating a reply"
          : "Reply ready"}
      </p>

    <div ref={bottomRef} />
  </div>
);
}
