"use client";

import ChatHeader from "./Header";
import MessageList from "./MessageList";
import ChatInput from "./Input";
import { ChatProvider } from "./ChatProvider";

import type { ChatOwner } from "./ChatProvider";
import type { Usage } from "@/types/chat";

export default function Chat({
  token,
  claim,
  owner,
  seedQuestion,
  onUsageChange,
  ownsViewport,
  showHeader = true,
  frame = "card",
}: {
  token?: string;
  claim?: string;
  // Read on the server and handed down, not imported: `@/lib/owner` reads the
  // environment at request time, and importing it here would pull it into the
  // browser bundle where the value would be frozen at build.
  owner: ChatOwner;
  // Puts a question in the composer on first render. The site links to
  // `/chat?about=...` from its project pages; this is where that lands.
  seedQuestion?: string;
  // Passed straight through to the provider, which is where usage lives. For
  // a host showing the allowance in its own header: the embed's page, and the
  // standalone site's top bar.
  onUsageChange?: (usage: Usage) => void;
  // False when this is a component of another page. Only the embed says so;
  // see `embed/src/element.tsx`.
  ownsViewport?: boolean;
  // False when the host page has a header of its own. The allowance the
  // header would have shown still reaches the host, through `onUsageChange`.
  showHeader?: boolean;
  // "card": a bordered, rounded, capped box, for a chat set into somebody
  // else's page — a dialog, a sidebar. "page": no box, for a host that gives
  // the chat the whole page and frames it itself; the transcript and composer
  // keep a readable column, and the host paints what is either side of it.
  frame?: "card" | "page";
}) {
  // Nothing is threaded through here any more. The three children read what
  // they each need from the provider, so adding something to the composer no
  // longer means touching a component that only ever passed it along.
  return (
    <ChatProvider
      token={token}
      claim={claim}
      owner={owner}
      seedQuestion={seedQuestion}
      onUsageChange={onUsageChange}
      ownsViewport={ownsViewport}
    >
      <div className="chat-root">
        <div
          className={
            frame === "card" ? "chat-frame chat-frame-card" : "chat-frame"
          }
        >
          {showHeader && <ChatHeader />}

          <MessageList />

          <ChatInput />
        </div>
      </div>
    </ChatProvider>
  );
}
