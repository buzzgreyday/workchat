"use client";

import { useEffect, useReducer } from "react";

import { greeting } from "@/lib/greeting";
import {
  initialTranscript,
  transcriptReducer,
} from "@/lib/transcript";
import type { SessionStatus } from "@/types/session";

/**
 * The transcript, and the one thing allowed to change it without a send.
 */
export function useTranscript({
  status,
  accessToken,
}: {
  status: SessionStatus;
  accessToken: string;
}) {
  // Lazily initialised from the real status and token rather than a blank: a
  // v1 link *is* the access token, so it is present on this first render and
  // the hirer should be greeted by name straight away. Seeding it empty would
  // show them the typing dots for a session that was never being opened.
  const [messages, dispatch] = useReducer(
    transcriptReducer,
    greeting(status, accessToken),
    initialTranscript,
  );

  // The greeting can only be personalised once a token exists, and with a
  // claim link that is one round trip after first paint. Telling the hirer
  // their link is spent goes through here too — the agent saying it reads
  // better than a banner. Whether the rewrite is still allowed is the
  // reducer's call; this only decides what it would say.
  useEffect(() => {
    dispatch({
      type: "greeting/set",
      greeting: greeting(status, accessToken),
    });
  }, [status, accessToken]);

  return { messages, dispatch };
}
