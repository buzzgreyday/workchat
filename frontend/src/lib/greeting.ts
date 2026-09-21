import { getUserName } from "@/lib/auth";
import {
  BROKEN_LINK_MESSAGE,
  hello,
  NO_LINK_MESSAGE,
  SPENT_LINK_MESSAGE,
} from "@/lib/copy";
import type { Greeting } from "@/lib/transcript";
import type { SessionStatus } from "@/types/session";

/**
 * What the greeting says, and whether it has anything to say yet.
 *
 * One function so the seed and the rewrite cannot drift: they are the same
 * decision made at two moments. An empty `content` with `status: "streaming"`
 * is what MessageBubble renders as the typing dots — the session is being
 * opened, and saying "Hi!" to nobody in particular while that happens is worse
 * than showing that something is underway.
 */
export function greeting(
  status: SessionStatus,
  accessToken: string,
): Greeting {
  if (status === "spent") {
    return {
      content: SPENT_LINK_MESSAGE,
      status: "complete",
    };
  }

  if (status === "error") {
    return {
      content: BROKEN_LINK_MESSAGE,
      status: "complete",
    };
  }

  if (status === "none") {
    return {
      content: NO_LINK_MESSAGE,
      status: "complete",
    };
  }

  if (!accessToken) {
    return { content: "", status: "streaming" };
  }

  return {
    content: hello(getUserName(accessToken)),
    status: "complete",
  };
}
