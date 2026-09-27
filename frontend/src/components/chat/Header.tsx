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
    <div className="bg-panel border-line border-b px-gutter-lg py-gutter">
      <div className="flex items-center gap-3">
        <div className="bg-avatar text-avatar-ink flex size-10 shrink-0 items-center justify-center rounded-full shadow-sm">
          <Bot size={20} />
        </div>

        <h1 className="text-heading text-title font-display">
            Workchat
        </h1>
        <p className={"font-sans"}>with {owner.name.toUpperCase()}</p>
      </div>

      {usage && <UsageBadge usage={usage} className="mt-3" />}
    </div>
  );
}