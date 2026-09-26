"use client";

import { useState } from "react";

import Chat from "@/components/chat/Chat";
import UsageBadge from "@/components/chat/UsageBadge";
import OwnerLinks from "@/components/OwnerLinks";
import type { Owner } from "@/lib/owner";
import type { Usage } from "@/types/chat";

/**
 * chat.mringdal.com: a top bar of this site's own, and the chat under it.
 *
 * The site is a host of the chat like any other, so it frames the chat the
 * way an embedding page would — `showHeader={false}`, the equivalent of
 * `header="none"`, and the allowance taken from `onUsageChange`, the same
 * number an embed hands out as `workchat-usage`. The chat's built-in header
 * is left for hosts that bring none.
 *
 * Rendered as two children of page.tsx's `<main>`, which is a container, so
 * the chat's 700px cap is decided by the space here rather than the window.
 * The bar keeps its height; the chat's wrapper takes what is left, up to the
 * cap, and `main` centres the pair.
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
      <header className="flex w-full max-w-chat shrink-0 flex-wrap items-center gap-x-4 gap-y-1">
        <h1 className="text-ink text-title font-display">
          Workchat with {owner.name}
        </h1>

        {usage && <UsageBadge usage={usage} />}

        <div className="ms-auto">
          <OwnerLinks owner={owner} />
        </div>
      </header>

      <div className="flex min-h-0 w-full max-w-chat flex-1 @min-[40rem]:max-h-[var(--card-max-height)]">
        <Chat
          token={token}
          claim={claim}
          owner={owner}
          showHeader={false}
          onUsageChange={setUsage}
        />
      </div>
    </>
  );
}
