import { ChatError } from "@/services/chat.service";

import {
  GENERIC_FAILURE_MESSAGE,
  LINK_EXPIRED_MESSAGE,
  OUT_OF_QUESTIONS_MESSAGE,
  rateLimitedMessage,
  SESSION_ENDED_MESSAGE,
} from "@/lib/copy";

/**
 * Did the *backend* refuse this for want of quota?
 *
 * Two things answer 429 and they mean opposite things to the person reading the
 * screen. Only the backend sends a detail with its refusal, so the presence of
 * that exact string is what distinguishes "you have none left", which is final,
 * from the rate limiter's "too fast", which clears by itself. Keying on the
 * status alone told a rate-limited hirer their questions were gone and shut the
 * composer on them.
 */
// Returns a plain boolean rather than a type predicate on purpose: narrowing to
// `error is ChatError` would make the *false* branch `never` at call sites that
// have already established the error is a ChatError, which is exactly where the
// rate-limit case needs to read retryAfter.
export function isQuotaExhausted(
  error: unknown,
): boolean {
  return (
    error instanceof ChatError &&
    error.status === 429 &&
    error.detail === "Query limit reached"
  );
}

/**
 * What to tell the hirer when a question fails.
 *
 * Worth the specificity: "you have used all your questions" and "something went
 * wrong" call for completely different reactions, and the previous single
 * catch-all message hedged between them and helped with neither.
 */
export function failureMessage(
  error: unknown,
): string {
  if (!(error instanceof ChatError)) {
    return GENERIC_FAILURE_MESSAGE;
  }

  if (error.status === 429) {
    return isQuotaExhausted(error)
      ? OUT_OF_QUESTIONS_MESSAGE
      : rateLimitedMessage(error.retryAfter);
  }

  if (error.status === 401) {
    return error.detail === "Token expired"
      ? LINK_EXPIRED_MESSAGE
      : SESSION_ENDED_MESSAGE;
  }

  return GENERIC_FAILURE_MESSAGE;
}
