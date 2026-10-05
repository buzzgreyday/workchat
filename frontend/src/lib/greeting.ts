import { getUserName } from "@/lib/auth";
import {
  BROKEN_LINK_MESSAGE,
  hello,
  NO_LINK_MESSAGE,
  NO_LINK_TRIAL_MESSAGE,
  SPENT_LINK_MESSAGE,
  TRIAL_FAILED_MESSAGE,
  trialGoneMessage,
  trialTriedMessage,
  trialUsedMessage,
} from "@/lib/copy";
import type { Greeting } from "@/lib/transcript";
import type { SessionStatus, TrialState } from "@/types/session";

// What the no-link greeting says, by how a trial stands. "starting" never
// reaches here: the session is "loading" then, which shows the typing dots.
const NO_LINK: Record<TrialState, (owner: string) => string> = {
  unavailable: () => NO_LINK_MESSAGE,
  available: () => NO_LINK_TRIAL_MESSAGE,
  starting: () => NO_LINK_TRIAL_MESSAGE,
  used: trialUsedMessage,
  tried: trialTriedMessage,
  gone: trialGoneMessage,
  failed: () => TRIAL_FAILED_MESSAGE,
};

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
  trial: TrialState = "unavailable",
  // Whose CV this is, for the messages that name them.
  owner = "",
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
      content: NO_LINK[trial](owner),
      status: "complete",
    };
  }

  if (!accessToken) {
    return { content: "", status: "streaming" };
  }

  return {
    content: hello(getUserName(accessToken), owner),
    status: "complete",
  };
}
