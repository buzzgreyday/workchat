import { Bot } from "lucide-react";

import { useControls } from "./ChatProvider";
import UsageBadge from "./UsageBadge";

/**
 * The chat's own header, for a host that has none.
 *
 * The default when embedded: a page that says nothing about headers gets this
 * one. A page with a header of its own passes `header="none"` and shows the
 * allowance itself — the standalone site does exactly that, in its top bar.
 */
export default function ChatHeader() {
  const { usage, owner } = useControls();

  return (
    <div className="chat-header">
      <div className="chat-header-row">
        <div className="chat-header-avatar">
          <Bot size={20} />
        </div>

        <h1 className="chat-title">
            Workchat
        </h1>
        <p className="chat-owner">with {owner.name.toUpperCase()}</p>
      </div>

      {usage && <UsageBadge usage={usage} />}
    </div>
  );
}