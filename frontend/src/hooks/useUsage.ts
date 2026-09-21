"use client";

import {
  useCallback,
  useEffect,
  useState,
} from "react";

import { sessionService } from "@/services/session.service";
import type { Usage } from "@/types/chat";
import type {
  AuthFetch,
  SessionStatus,
} from "@/types/session";

/** How many questions are left on this link, and keeping that honest. */
export function useUsage({
  status,
  accessToken,
  authFetch,
}: {
  status: SessionStatus;
  accessToken: string;
  authFetch: AuthFetch;
}) {
  const [usage, setUsage] =
    useState<Usage | null>(null);

  // Ask the server what is left. Spends nothing, which is what /session is for
  // — so it is safe both on arrival and after a turn that failed without ever
  // reporting its usage.
  const refresh = useCallback(async () => {
    try {
      const info =
        await sessionService.get(authFetch);
      setUsage(info.usage);
    } catch {
      // Not worth surfacing: the count is a nicety, and any real problem with
      // the session shows up the moment a question is asked.
    }
  }, [authFetch]);

  // The allowance on arrival, so the header can show "5 / 5 questions left"
  // instead of staying blank until the first answer comes back.
  //
  // Written as a promise callback rather than `void refresh()` so the state
  // write is visibly a response to something outside React finishing, which
  // is what it is. The `cancelled` flag is the part that was missing: a token
  // that changes mid-flight would otherwise have the previous grant's
  // allowance land on top of the new one's.
  useEffect(() => {
    if (status !== "ready" || !accessToken) {
      return;
    }

    let cancelled = false;

    sessionService
      .get(authFetch)
      .then((info) => {
        if (!cancelled) {
          setUsage(info.usage);
        }
      })
      .catch(() => {
        // Same reasoning as `refresh` above: a count that failed to arrive is
        // not worth telling anyone about.
      });

    return () => {
      cancelled = true;
    };
  }, [status, accessToken, authFetch]);

  /**
   * The allowance is gone, recorded without asking the server.
   *
   * Only a *quota* 429 may call this — never a rate-limit 429, which would
   * strand someone at zero questions they still have. The caller draws that
   * distinction with `isQuotaExhausted`; this only writes down the answer.
   */
  const markExhausted = useCallback(() => {
    setUsage((prev) =>
      prev
        ? { ...prev, remaining: 0, used: prev.max }
        : prev,
    );
  }, []);

  return {
    usage,
    setUsage,
    refresh,
    markExhausted,
  };
}
