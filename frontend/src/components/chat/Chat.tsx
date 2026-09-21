"use client";

import ChatHeader from "./Header";
import MessageList from "./MessageList";
import ChatInput from "./Input";
import { ChatProvider } from "./ChatProvider";

import type { Owner } from "@/lib/owner";

export default function Chat({
  token,
  claim,
  owner,
}: {
  token?: string;
  claim?: string;
  // Read on the server and handed down, not imported: `@/lib/owner` reads the
  // environment at request time, and importing it here would pull it into the
  // browser bundle where the value would be frozen at build.
  owner: Owner;
}) {
  // Nothing is threaded through here any more. The three children read what
  // they each need from the provider, so adding something to the composer no
  // longer means touching a component that only ever passed it along.
  //
  // `h-full` rather than repeating the viewport arithmetic: the shell is one
  // viewport tall and owns the padding, so the card just fills what it is
  // given. Two places subtracting the same 2rem is how the two drift apart.
  //
  // `sm:max-h-175` rather than `max-h-175`: the 700px cap sits below a modern
  // phone's viewport, so applying it everywhere left a band of dead background
  // above and below the card on exactly the screens with least to spare.
  return (
    <ChatProvider
      token={token}
      claim={claim}
      owner={owner}
    >
      <div className="bg-panel border-line flex h-full w-full max-w-chat flex-col overflow-hidden rounded-card border shadow-2xl sm:max-h-[var(--card-max-height)]">
        <ChatHeader />

        <MessageList />

        <ChatInput />
      </div>
    </ChatProvider>
  );
}
