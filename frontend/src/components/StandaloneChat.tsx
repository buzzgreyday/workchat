"use client";

import { useState } from "react";

import Chat from "@/components/chat/Chat";
import UsageBadge from "@/components/chat/UsageBadge";
import OwnerLinks from "@/components/OwnerLinks";
import type { Owner } from "@/lib/owner";
import type { Usage } from "@/types/chat";

/**
 * chat.mringdal.com: the whole page is the chat.
 *
 * A top bar with the title and the questions left, the chat filling the rest,
 * and a footer with the profile links. The site is a host of the chat like
 * any other, so it frames the chat the way an embedding page would —
 * `showHeader={false}`, the equivalent of `header="none"`, with the allowance
 * taken from `onUsageChange`, the number an embed hands out as
 * `workchat-usage` — and asks for `frame="page"`: no card, since there is
 * nothing around the chat for a card to sit in.
 *
 * The chat's band is `--site-chat-bg` edge to edge; the transcript and composer
 * keep their readable column inside it. The bars are the page's own colour.
 * Rendered as the three children of page.tsx's `<main>`.
 */
export default function StandaloneChat({
  token,
  claim,
  owner,
}: {
  token?: string;
  claim?: string;
  owner: Owner;
}) {
  const [usage, setUsage] = useState<Usage | null>(null);

  return (
    <>
      {/* Wraps rather than squeezing: on a phone the count drops to a line of
          its own instead of breaking the title in two. */}
      <header className="shell-top shell-sides flex w-full shrink-0 flex-wrap items-center gap-x-4 gap-y-1 border-b border-[var(--site-bar-border)] bg-[var(--site-bar-bg)] pb-3">
        <h1 className="text-heading text-title font-display">
          Workchat
        </h1>
        {usage && (
          <UsageBadge usage={usage} className="ms-auto shrink-0" />
        )}
      </header>

      <div className="shell-sides-bleed flex bg-[var(--site-chat-bg)] min-h-0 w-full flex-1 justify-center">
        <Chat
          token={token}
          claim={claim}
          owner={owner}
          showHeader={false}
          frame="page"
          onUsageChange={setUsage}
        />
      </div>

      {/* `site-footer` steps aside while the on-screen keyboard is up, so the
          composer sits right on it — see globals.css.

          No links configured, no footer — rather than an empty strip. The
          chat's band then reaches the bottom, which is padded instead. */}
      {owner.githubUrl || owner.linkedinUrl ? (
        <footer className="site-footer shell-bottom shell-sides flex w-full shrink-0 justify-center border-t border-[var(--site-footer-border)] bg-[var(--site-footer-bg)] pt-2">
          <OwnerLinks owner={owner} />
        </footer>
      ) : (
        <div className="site-footer shell-bottom w-full shrink-0 bg-[var(--site-chat-bg)]" />
      )}
    </>
  );
}
