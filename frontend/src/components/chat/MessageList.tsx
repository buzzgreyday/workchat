import MessageBubble from "./MessageBubble";
import { useAutoScroll } from "@/hooks/useAutoScroll";
import { useTranscriptContext } from "./ChatProvider";


// Rendering each message, no fetch, jwt, etc. Reads the transcript context
// rather than taking a prop, so the token-by-token re-render it cannot avoid
// stops at this subtree instead of reaching the header and the composer too.
export default function MessageList() {
  const { messages } = useTranscriptContext();

  const { containerRef } = useAutoScroll(messages);

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
      // `min-h-0` because a flex item's automatic minimum size is its content:
      // without it this box refuses to shrink below the whole transcript and
      // the card's `overflow-hidden` is the only thing hiding the difference.
      // `overscroll-contain` keeps a flick at either end of the transcript from
      // chaining out into the document behind it.
      className="min-h-0 flex-1 overflow-y-auto overscroll-contain p-gutter-lg space-y-4"
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
  </div>
);
}
