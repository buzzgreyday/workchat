import type { Usage } from "@/types/chat";

/**
 * How many questions are left, as a pill.
 *
 * Shared by the chat's own header and by a page that shows the allowance in a
 * header of its own — the standalone site's top bar — so the two cannot drift
 * into two ways of saying the same number.
 */
export default function UsageBadge({
  usage,
}: {
  usage: Usage;
}) {
  return (
    <span className="usage-badge chat-ui">
      {usage.remaining} / {usage.max} questions left
    </span>
  );
}
