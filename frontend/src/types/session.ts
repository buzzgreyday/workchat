/**
 * What a session is, as a type.
 *
 * These two lived in `useSession.ts`, which meant the service layer imported
 * them from a hook — `chat.service.ts` and `session.service.ts` both did — and
 * so did every pure module that wanted to say "given a session status…".
 * A fetch wrapper and a five-way enum are not React, and a module that is not
 * React should not have to import one to name them.
 */

export type SessionStatus =
  | "loading"
  | "ready"
  // The claim link was already spent. Single use, so only a new link helps.
  | "spent"
  // A credential was presented and could not be turned into a session.
  | "error"
  // No credential at all, and no cookie left to resume from.
  | "none";

/**
 * `fetch`, with the access token on it and one refresh-and-retry behind it.
 *
 * Handed to the services rather than imported by them, so nothing below this
 * line has to know how a token is obtained or renewed.
 */
export type AuthFetch = (
  input: string,
  init?: RequestInit,
) => Promise<Response>;
