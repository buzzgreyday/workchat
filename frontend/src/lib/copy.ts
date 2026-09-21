/**
 * Everything this app says to a person, in one file.
 *
 * Not a filing preference. These strings were interleaved with fetch
 * orchestration in a 462-line hook, so changing what the page says to someone
 * whose link has expired meant reading streaming code to find it — and nobody
 * could read them all at once to check they sound like one voice. Nothing here
 * imports anything, which is the point: it is a script, not logic.
 */

export const SPENT_LINK_MESSAGE =
  "This chat link has already been used, so I can't start a new session with it. " +
  "Links are single use — ask for a fresh one and I'll pick up from there.";

export const BROKEN_LINK_MESSAGE =
  "I couldn't open a session from this link. It may have expired. " +
  "Ask for a fresh one and we can get started.";

export const OUT_OF_QUESTIONS_MESSAGE =
  "That's all the questions on this link — you've used them up. " +
  "Ask for a new link if there's more you'd like to know.";

export const SESSION_ENDED_MESSAGE =
  "This session has ended, so I can't answer that one. " +
  "Ask for a fresh link and we can carry on.";

export const LINK_EXPIRED_MESSAGE =
  "This link has expired, so I can't answer that one. " +
  "Ask for a fresh one and we can carry on.";

export const GENERIC_FAILURE_MESSAGE =
  "Something went wrong answering that — it's not you. Try again in a moment.";

export const NO_LINK_MESSAGE =
  "You'll need the chat link you were sent to start a session. " +
  "If you had one open, it may just have timed out — ask for a new link.";

/**
 * Why the composer is shut.
 *
 * Short because they are placeholders, and a placeholder is laid out *inside* a
 * one-row textarea: anything that wraps makes the field two lines tall and
 * scrollable before a character has been typed. The long version of each is
 * already in the transcript, which is where there is room for it.
 *
 * Still two strings rather than one. Running out of questions and never having
 * had a session are both dead ends, but telling someone whose session is fine
 * that their link is broken is the wrong dead end.
 */
export const NO_QUESTIONS_LEFT = "No questions left";
export const NO_SESSION = "Link can't start a session";

/** The composer's prompt. Short for the same reason as the two above. */
export const COMPOSER_PLACEHOLDER = "Ask a question…";

/** The greeting, once there is a name to use. */
export function hello(name: string): string {
  return `Hi ${name}! 👋`;
}

/**
 * Turned away by the rate limiter, with the wait if the response named one.
 *
 * Deliberately reassuring about the allowance: this is the refusal that does
 * *not* cost a question, and someone who has just been told "no" has no way to
 * know that unless it says so.
 */
export function rateLimitedMessage(
  retryAfter: number | null,
): string {
  const wait = retryAfter
    ? `about ${retryAfter} second${retryAfter === 1 ? "" : "s"}`
    : "a moment";

  return (
    `That came through a bit quickly, so it didn't go anywhere. ` +
    `Give it ${wait} and ask again — your questions are all still there.`
  );
}
