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
  | "spent"
  | "error";

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

  const [status, setStatus] =
    useState<SessionStatus>(() => {
      if (claim) return "loading";
      if (token) return "ready";
      return "error";
    });

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

  // v1 links have nothing to refresh with.
  const canRefresh = Boolean(claim);

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
  const exchanged = useRef(false);

  useEffect(() => {
    if (!claim || exchanged.current) {
      return;
    }

    exchanged.current = true;

    let cancelled = false;

    (async () => {
      try {
        const session =
          await authService.claim(claim);

        if (cancelled) return;

        apply(session);
        setStatus("ready");
      } catch (error) {
        if (cancelled) return;

        setStatus(
          error instanceof AuthError &&
            error.status === 409
            ? "spent"
            : "error",
        );
      } finally {
        if (!cancelled) {
          stripCredentialParams();
        }
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [claim, apply]);

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
