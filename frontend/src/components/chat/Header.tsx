import { Bot } from "lucide-react";

import { useControls } from "./ChatProvider";

export default function ChatHeader() {
  const { usage, owner } = useControls();

  return (
    <div className="bg-panel border-line border-b px-gutter-lg py-gutter">
      <div className="flex items-center gap-3">
        <div className="bg-accent text-on-accent flex size-10 shrink-0 items-center justify-center rounded-full shadow-sm">
          <Bot size={20} />
        </div>

        <h1 className="text-ink text-title font-display">
          WORKCHAT WITH {owner.name.toUpperCase()}
        </h1>
      </div>

      {usage && (
        <span className="bg-panel-raised text-ink-muted mt-3 inline-block rounded-full px-3 py-1 text-micro shadow-sm">
          {usage.remaining} / {usage.max} questions left
        </span>
      )}
    </div>
  );
}