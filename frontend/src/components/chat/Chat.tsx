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
}) {
  // Nothing is threaded through here any more. The three children read what
  // they each need from the provider, so adding something to the composer no
  // longer means touching a component that only ever passed it along.
  //
  // `h-full` rather than repeating the viewport arithmetic: the shell is one
  // viewport tall and owns the padding, so the card just fills what it is
  // given. Two places subtracting the same 2rem is how the two drift apart.
  //
  // The 700px cap applies from a 40rem-wide *container*, not a 40rem window.
  // It sits below a modern phone's viewport, so applying it everywhere left a
  // band of dead background above and below the card on exactly the screens
  // with least to spare. And measured on the window it was wrong once
  // embedded: a chat in a narrow dialog on a wide screen was capped as though
  // it had the whole desktop. Responsive rules inside the chat use container
  // variants (`@min-[…]:`), never viewport ones (`sm:`), for the same reason.
  return (
    <ChatProvider
      token={token}
      claim={claim}
      owner={owner}
      seedQuestion={seedQuestion}
      onUsageChange={onUsageChange}
      ownsViewport={ownsViewport}
    >
      <div className="@container flex h-full w-full items-center justify-center">
        <div className="bg-panel border-line flex h-full w-full max-w-chat flex-col overflow-hidden rounded-card border shadow-2xl @min-[40rem]:max-h-[var(--card-max-height)]">
          {showHeader && <ChatHeader />}

          <MessageList />

          <ChatInput />
        </div>
      </div>
    </ChatProvider>
  );
}
