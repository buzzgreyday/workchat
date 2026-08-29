"use client";

import {
  useCallback,
  useEffect,
  useRef,
  useState,
} from "react";

import {
  AuthError,
  authService,
  Session,
} from "@/services/auth.service";

export type SessionStatus =
  | "loading"
  | "ready"
  // The claim link was already spent. Single use, so only a new link helps.
  | "spent"
  // A credential was presented and could not be turned into a session.
  | "error"
  // No credential at all, and no cookie left to resume from.
  | "none";

export type AuthFetch = (
  input: string,
  init?: RequestInit,
) => Promise<Response>;

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
        if (!cancelled && claim) {
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

  return {
    accessToken,
    status,
    authFetch,
  };
}
