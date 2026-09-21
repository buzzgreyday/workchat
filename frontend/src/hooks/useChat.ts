"use client";

import { useState } from "react";

import { getGrantId } from "@/lib/auth";
import {
  GENERIC_FAILURE_MESSAGE,
  NO_QUESTIONS_LEFT,
  NO_SESSION,
} from "@/lib/copy";
import {
  failureMessage,
  isQuotaExhausted,
} from "@/lib/failure";
import { useConversationMemory } from "@/hooks/useConversationMemory";
import { useTranscript } from "@/hooks/useTranscript";
import { useUsage } from "@/hooks/useUsage";
import { chatService } from "@/services/chat.service";
import type { AuthFetch, SessionStatus } from "@/types/session";

/**
 * One turn of the conversation, end to end.
 *
 * What is left here is orchestration and nothing else: what the transcript,
 * the allowance and the stored conversation have to say to one another while a
 * question is in flight. The copy, the error-to-copy mapping, the greeting,
 * the transcript reducer, the persistence and the usage polling all moved out,
 * and each of them can now be read — and changed — without reading this.
 */
export function useChat({
  accessToken,
  status,
  authFetch,
}: {
  accessToken: string;
  status: SessionStatus;
  authFetch: AuthFetch;
}) {
  // Hook order is load-bearing. The greeting rewrite is an effect inside
  // `useTranscript` and the sessionStorage restore is one inside
  // `useConversationMemory`; effects run in the order their hooks were called,
  // and a restored transcript has to be the last word on what is on screen.
  const { messages, dispatch } = useTranscript({
    status,
    accessToken,
  });

  const {
    usage,
    setUsage,
    refresh: refreshUsage,
    markExhausted,
  } = useUsage({ status, accessToken, authFetch });

  // Derived, never stored. A turn that broke leaves its bubble `error`, and
  // `loading` falling out of that is exactly what reopens the composer without
  // anything having to remember to.
  const loading =
    messages.at(-1)?.status === "streaming";

  // Which hirer this transcript belongs to. Everything cached is keyed on it,
  // so a second link opened in the same tab starts clean rather than showing
  // the previous one's questions.
  const grantId = accessToken
    ? getGrantId(accessToken)
    : "";

  const { memory, remember } =
    useConversationMemory({
      grantId,
      messages,
      dispatch,
      settled: !loading,
    });

  const [input, setInput] = useState("");

  // Nothing to send with, so the composer stays shut rather than letting the
  // hirer type a question into a 401 — or into a 429, once the allowance is
  // known to be gone.
  const outOfQuestions = usage?.remaining === 0;
  const disabled =
    status !== "ready" || outOfQuestions;

  const disabledReason = !disabled
    ? null
    : outOfQuestions
      ? NO_QUESTIONS_LEFT
      : NO_SESSION;

  const sendMessage = async (
    question?: string,
  ) => {
    const text =
      typeof question === "string"
        ? question.trim()
        : input.trim();

    if (!text || loading || disabled) {
      return;
    }

    dispatch({
      type: "user/asked",
      id: crypto.randomUUID(),
      content: text,
      at: new Date(),
    });

    setInput("");

    try {
      dispatch({
        type: "assistant/opened",
        id: crypto.randomUUID(),
        at: new Date(),
      });

      await chatService.stream(
        authFetch,
        {
          message: text,
          history: memory.history,
          conversation_id: memory.conversationId,
        },
        {
          onToken(value) {
            dispatch({
              type: "assistant/token",
              value,
            });
          },

          onDone(
            nextHistory,
            nextUsage,
            nextConversationId,
          ) {
            setUsage(nextUsage);

            // The id only arrives on the first turn; later frames carry null
            // and must not erase the one already held, or the next question
            // opens a second conversation for the same person.
            remember({
              type: "remembered",
              memory: {
                history: nextHistory,
                conversationId:
                  nextConversationId ??
                  memory.conversationId,
              },
            });

            dispatch({
              type: "assistant/completed",
            });
          },

          // The turn broke. The backend sends this frame rather than just
          // stopping, precisely so a failure is distinguishable from a dropped
          // connection — and it carries a string already fit to show someone.
          onError(message) {
            dispatch({
              type: "assistant/failed",
              content:
                message ||
                GENERIC_FAILURE_MESSAGE,
            });

            // The question was already paid for — quota is spent before the
            // model is called — but usage only rides a `done` frame, so the
            // header is a turn behind until this puts it right.
            void refreshUsage();
          },
        },
      );
    } catch (error) {
      console.error(error);

      // Only a *quota* 429 means the allowance is gone. Never a rate-limit
      // 429, which would strand someone at zero questions they still have.
      if (isQuotaExhausted(error)) {
        markExhausted();
      }

      dispatch({
        type: "assistant/failed",
        content: failureMessage(error),
      });
    }
  };

  return {
    messages,
    input,
    loading,
    disabled,
    disabledReason,
    usage,

    setInput,
    sendMessage,
  };
}
