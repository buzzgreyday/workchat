import { ArrowDown } from "lucide-react";

import MessageBubble from "./MessageBubble";
import { useAutoScroll } from "@/hooks/useAutoScroll";
import { RETRY } from "@/lib/copy";
import { useControls, useTranscriptContext } from "./ChatProvider";

// Rendering each message, no fetch, jwt, etc. Reads the transcript context
// rather than taking a prop, so the token-by-token re-render it cannot avoid
// stops at this subtree instead of reaching the header and the composer too.
export default function MessageList() {
  const { messages } = useTranscriptContext();
  const { canRetry, retry } = useControls();

  const { containerRef, spacerRef, atEnd, toEnd } = useAutoScroll(messages);

  const awaitingReply = messages.at(-1)?.status === "streaming";

  return (
    // A frame round the transcript, for the button to sit over its foot
    // without scrolling with it.
    <div className="chat-log-frame">
      <div
        ref={containerRef}
        // `log` rather than a live region around the text: a reply arrives a
        // token at a time, and announcing each one would read the answer out
        // character by character. The status line below says what is happening
        // instead, which is the part a screen reader actually needs.
        role="log"
        aria-label="Conversation"
        className="chat-log"
        // A part (EMBED.md): the scrolling conversation, so a host can set its
        // margins and its scrollbar.
        part="transcript"
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

        {/* The room under the newest question (useAutoScroll), so it can be
          scrolled to the top however short its reply. */}
        <div ref={spacerRef} aria-hidden="true" className="chat-log-spacer" />
      </div>

      {/* To the end, once there is more below than shows. Not rendered
          otherwise, rather than hidden, so it is no stop for a keyboard
          while there is nowhere to go. A part (EMBED.md), for a host to
          style. */}
      {!atEnd && (
        <button
          type="button"
          onClick={toEnd}
          aria-label="Go to the latest"
          className="chat-jump"
          part="jump"
        >
          <ArrowDown size={18} aria-hidden="true" />
        </button>
      )}
    </div>
  );
}
