"use client";

import { useState } from "react";

import Chat from "@/components/chat/Chat";
import UsageBadge from "@/components/chat/UsageBadge";
import OwnerLinks, { hasOwnerLinks } from "@/components/OwnerLinks";
import RollingTitle from "@/components/RollingTitle";
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
      <header className="site-bar shell-top shell-sides">
        <h1 className="chat-title site-title">
          <RollingTitle text="Workchat" />
        </h1>
        {usage && (
          <UsageBadge usage={usage} />
        )}
      </header>

      <div className="site-chat shell-sides-bleed">
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
      {hasOwnerLinks(owner) ? (
        <footer className="site-footer site-footer-links shell-bottom shell-sides">
          <OwnerLinks owner={owner} />
        </footer>
      ) : (
        <div className="site-footer site-footer-empty shell-bottom" />
      )}
    </>
  );
}
