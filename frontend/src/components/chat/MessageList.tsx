import { ArrowDown } from "lucide-react";
import type { ReactNode } from "react";

import MessageBubble from "./MessageBubble";
import { useScrollToQuestion } from "@/hooks/useScrollToQuestion";
import { RETRY } from "@/lib/copy";
import { useControls, useTranscriptContext } from "./ChatProvider";

// Rendering each message, no fetch, jwt, etc. Reads the transcript context
// rather than taking a prop, so the token-by-token re-render it cannot avoid
// stops at this subtree instead of reaching the header and the composer too —
// the composer is handed in as `footer`, an element made by the parent, which
// a re-render here passes on untouched.
export default function MessageList({ footer }: { footer?: ReactNode }) {
  const { messages } = useTranscriptContext();
  const { canRetry, retry } = useControls();

  const { containerRef, toEnd } = useScrollToQuestion(messages);

  const awaitingReply = messages.at(-1)?.status === "streaming";

  return (
    // What scrolls: the messages, and the box to type in held at its foot,
    // so the conversation runs on behind the box to the bottom of the chat
    // and fades out under it (styles/chat.css). A part (EMBED.md), for a host
    // to set the margin round both.
    <div ref={containerRef} className="chat-log" part="transcript">
      <div
        // `log` rather than a live region around the text: a reply arrives a
        // token at a time, and announcing each one would read the answer out
        // character by character. The status line below says what is happening
        // instead, which is the part a screen reader actually needs. The
        // messages alone, not the box to type in under them.
        role="log"
        aria-label="Conversation"
        className="chat-messages"
      >
        {messages.map((message) => (
          <MessageBubble key={message.id} message={message} />
        ))}

        {canRetry && (
          <button
            type="button"
            onClick={() => retry()}
            className="button button-wide button-retry"
          >
            {RETRY}
          </button>
        )}

        <p role="status" className="visually-hidden">
          {awaitingReply ? "Generating a reply" : "Reply ready"}
        </p>
      </div>

      {/* Held to the foot of what scrolls: the box to type in, and over it
          the button to the end. */}
      <div className="chat-dock">
        {/* To the end, while there is more below than shows. Always here,
            and shown or hidden by CSS from the scroll position — hidden, it
            is no stop for a keyboard either. A part (EMBED.md), for a host to
            style. */}
        <button
          type="button"
          onClick={toEnd}
          aria-label="Go to the latest"
          className="chat-jump"
          part="jump"
        >
          <ArrowDown size={18} strokeWidth={2.5} aria-hidden="true" />
        </button>

        {footer}
      </div>
    </div>
  );
}
