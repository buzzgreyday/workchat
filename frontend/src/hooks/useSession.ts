"use client";

import {
  useCallback,
  useEffect,
  useRef,
  useState,
} from "react";

import { solve } from "@/lib/pow";
import {
  AuthError,
  authService,
  Session,
} from "@/services/auth.service";

import type {
  AuthFetch,
  SessionStatus,
  TrialState,
} from "@/types/session";

// Re-exported because this is where the rest of the app has always imported
// them from, and moving the declaration is not a reason to make every caller
// move with it. `export type`, not a bare re-export: `isolatedModules` cannot
// tell a type from a value across a module boundary otherwise.
export type {
  AuthFetch,
  SessionStatus,
  TrialState,
};

/**
 * Strip the credential out of the address bar.
 *
 * Rebuilt from the real URL rather than reset to `pathname` so any other query
 * parameter survives. Runs after the exchange has settled, not before: on
 * success the claim is spent, on failure it is dead, and either way leaving it
 * there would re-fire the exchange on the next reload.
 */
function stripCredentialParams(): void {
  const url = new URL(window.location.href);
  const keys = ["token", "claim"];

  if (
    !keys.some((key) =>
      url.searchParams.has(key),
    )
  ) {
    return;
  }

  keys.forEach((key) =>
    url.searchParams.delete(key),
  );

  window.history.replaceState(
    {},
    "",
    `${url.pathname}${url.search}${url.hash}`,
  );
}

// The backend's refusals of a trial, by the `detail` each carries — the
// strings are the contract (backend/app/common/exceptions.py), as "Query
// limit reached" is for the quota.
const TRIED = "Trial already used in this browser";

const TRIAL_REFUSALS: Record<string, TrialState> = {
  "Trial already used today": "used",
  [TRIED]: "tried",
  "Trial budget reached": "gone",
};

/**
 * Owns the access token and how it gets renewed.
 *
 * Two shapes, decided by which parameter the link carried:
 *
 *  - `token` (v1) — the link *is* the access token. Long-lived, nothing to
 *    renew, and a 401 is final.
 *  - `claim` (v2) — the link is exchanged once for a short-lived access token
 *    held here in memory plus a refresh cookie the page cannot read. A 401
 *    triggers one refresh and one retry.
 *  - neither — a reload. The claim was stripped from the URL when it was spent,
 *    so the cookie is all that is left, and resuming from it is the difference
 *    between F5 being free and F5 costing the hirer their only link.
 */
export function useSession({
  token,
  claim,
}: {
  token?: string;
  claim?: string;
}) {
  const [accessToken, setAccessToken] =
    useState<string>(token ?? "");

  // A v1 link is the access token, so it is ready on arrival. Anything else has
  // a round trip to make first — exchanging a claim, or resuming from the cookie
  // a previous claim left behind.
  const isV1 = Boolean(token);

  const [status, setStatus] =
    useState<SessionStatus>(
      isV1 ? "ready" : "loading",
    );

  // Read inside authFetch, which must see the newest token without being
  // re-created (and re-triggering every consumer) each time one arrives.
  const accessTokenRef = useRef(accessToken);

  const apply = useCallback(
    (session: Session) => {
      accessTokenRef.current =
        session.access_token;
      setAccessToken(session.access_token);
    },
    [],
  );

  // v1 links have nothing to refresh with; every other case is cookie-backed.
  const canRefresh = !isV1;

  // Single-flight: parallel 401s share one refresh instead of racing. Racing is
  // what the server reads as a replay, and outside its grace window that cuts
  // the grant and locks the hirer out for good.
  const inFlight = useRef<Promise<string> | null>(
    null,
  );

  const refresh =
    useCallback(async (): Promise<string> => {
      if (inFlight.current) {
        return inFlight.current;
      }

      const attempt = (async () => {
        try {
          try {
            const session =
              await authService.refresh();
            apply(session);
            return session.access_token;
          } catch (error) {
            // 409 means another tab rotated first. That tab has already written
            // the successor to the shared cookie jar, so one retry picks it up.
            if (
              error instanceof AuthError &&
              error.status === 409
            ) {
              const session =
                await authService.refresh();
              apply(session);
              return session.access_token;
            }

            throw error;
          }
        } finally {
          inFlight.current = null;
        }
      })();

      inFlight.current = attempt;

      return attempt;
    }, [apply]);

  const authFetch = useCallback<AuthFetch>(
    async (input, init = {}) => {
      const send = (bearer: string) =>
        fetch(input, {
          ...init,
          headers: {
            ...(init.headers ?? {}),
            Authorization: `Bearer ${bearer}`,
          },
        });

      const response = await send(
        accessTokenRef.current,
      );

      if (
        response.status !== 401 ||
        !canRefresh
      ) {
        return response;
      }

      // Safe to re-send: nothing has read the body yet, and the access token is
      // the only part of the request that changes.
      try {
        return await send(await refresh());
      } catch {
        setStatus("spent");
        return response;
      }
    },
    [canRefresh, refresh],
  );

  // Guards against React StrictMode invoking this effect twice in development.
  // The claim is single use, so the second exchange would 409 and show a working
  // session as spent.
  const opened = useRef(false);

  useEffect(() => {
    if (isV1 || opened.current) {
      return;
    }

    opened.current = true;

    let cancelled = false;

    (async () => {
      try {
        // With a claim, exchange it. Without one, the refresh cookie an earlier
        // claim left behind is the only way in — and that is what an ordinary
        // reload looks like, since the claim is stripped from the URL as soon as
        // it is spent. Treating a bare URL as a dead end would mean F5 costing
        // the hirer their session, and with a single-use link there would be no
        // way back from that.
        const session = claim
          ? await authService.claim(claim)
          : await authService.refresh();

        if (cancelled) return;

        apply(session);
        setStatus("ready");
      } catch (error) {
        if (cancelled) return;

        const spent =
          error instanceof AuthError &&
          error.status === 409;

        setStatus(
          spent
            ? "spent"
            : claim
              ? "error"
              : "none",
        );
      } finally {
        // Whenever a claim came in at all — an empty one too. `?claim=` with
        // nothing after it (a link cut short, an address bar autocompleting
        // one) is no claim to exchange, and went down the refresh path above,
        // but it is still no reason to leave a dangling `?claim=` in the
        // address. `undefined` means none was given: an embed with no `claim`
        // attribute leaves its host page's address alone.
        if (!cancelled && claim !== undefined) {
          stripCredentialParams();
        }
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [claim, isV1, apply]);

  // The v1 token needs the same treatment, minus the exchange.
  useEffect(() => {
    if (token) {
      stripCredentialParams();
    }
  }, [token]);

  // --- guest trial --------------------------------------------------------
  //
  // Only for someone who arrived with nothing: no link, and no cookie to
  // resume from. Whether one is on offer is asked of the backend rather than
  // configured here, so switching trials off is a backend setting and nothing
  // a host page has to know about.
  const [trial, setTrial] =
    useState<TrialState>("unavailable");

  useEffect(() => {
    if (status !== "none" || trial !== "unavailable") {
      return;
    }

    let cancelled = false;

    // A 404 means trials are off, and anything else failing means we cannot
    // tell: either way nothing is offered, and the no-link message stands.
    // The one refusal worth saying out loud is a browser that has had its
    // trial — that is an answer, not a failure.
    authService.trialChallenge().then(
      () => !cancelled && setTrial("available"),
      (error) =>
        !cancelled &&
        error instanceof AuthError &&
        error.message === TRIED &&
        setTrial("tried"),
    );

    return () => {
      cancelled = true;
    };
  }, [status, trial]);

  // A second press while one is under way must not solve or post twice.
  const starting = useRef(false);

  const startTrial = useCallback(async () => {
    if (starting.current) {
      return;
    }

    starting.current = true;
    setTrial("starting");
    // The greeting shows the typing dots while this runs.
    setStatus("loading");

    try {
      // A fresh challenge, not one fetched when the button appeared: it would
      // have aged by however long the visitor read the page first, and a
      // challenge is only good for minutes.
      const solution = await solve(
        await authService.trialChallenge(),
      );
      const session = await authService.trial(solution);

      apply(session);
      setStatus("ready");
      setTrial("unavailable");
    } catch (error) {
      setStatus("none");
      setTrial(
        error instanceof AuthError
          ? (TRIAL_REFUSALS[error.message] ?? "failed")
          : "failed",
      );
    } finally {
      starting.current = false;
    }
  }, [apply]);

  return {
    accessToken,
    status,
    authFetch,
    trial,
    startTrial,
  };
}
