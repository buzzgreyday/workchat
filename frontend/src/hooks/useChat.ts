"use client";

import { useEffect, useState } from "react";

import { chatService, ChatError } from "@/services/chat.service";
import { sessionService } from "@/services/session.service";
import { getUserName } from "@/lib/auth";
import { Message, ChatHistoryMessage, Usage } from "@/types/chat";
import { AuthFetch, SessionStatus } from "@/hooks/useSession";

const SPENT_LINK_MESSAGE =
  "This chat link has already been used, so I can't start a new session with it. " +
  "Links are single use — ask for a fresh one and I'll pick up from there.";

const BROKEN_LINK_MESSAGE =
  "I couldn't open a session from this link. It may have expired. " +
  "Ask for a fresh one and we can get started.";

const OUT_OF_QUESTIONS_MESSAGE =
  "That's all the questions on this link — you've used them up. " +
  "Ask for a new link if there's more you'd like to know.";

const SESSION_ENDED_MESSAGE =
  "This session has ended, so I can't answer that one. " +
  "Ask for a fresh link and we can carry on.";

const LINK_EXPIRED_MESSAGE =
  "This link has expired, so I can't answer that one. " +
  "Ask for a fresh one and we can carry on.";

const GENERIC_FAILURE_MESSAGE =
  "Something went wrong answering that — it's not you. Try again in a moment.";

/**
 * What to tell the hirer when a question fails.
 *
 * Worth the specificity: "you have used all your questions" and "something went
 * wrong" call for completely different reactions, and the previous single
 * catch-all message hedged between them and helped with neither.
 */
function failureMessage(error: unknown): string {
  if (!(error instanceof ChatError)) {
    return GENERIC_FAILURE_MESSAGE;
  }

  if (error.status === 429) {
    return OUT_OF_QUESTIONS_MESSAGE;
  }

  if (error.status === 401) {
    return error.detail === "Token expired"
      ? LINK_EXPIRED_MESSAGE
      : SESSION_ENDED_MESSAGE;
  }

  return GENERIC_FAILURE_MESSAGE;
}

const NO_LINK_MESSAGE =
  "You'll need the chat link you were sent to start a session. " +
  "If you had one open, it may just have timed out — ask for a new link.";

export function useChat({
  accessToken,
  status,
  authFetch,
}: {
  accessToken: string;
  status: SessionStatus;
  authFetch: AuthFetch;
}) {
  const [messages, setMessages] = useState<Message[]>([
    {
      id: "welcome",
      role: "assistant",
      content: "Hi! 👋",
      createdAt: new Date(0),
      status: "complete",
    },
  ]);

  // The greeting can only be personalised once a token exists, and with a claim
  // link that is one round trip after first paint. Telling the hirer their link
  // is spent goes here too — the agent saying it reads better than a banner.
  useEffect(() => {
    const content =
      status === "spent"
        ? SPENT_LINK_MESSAGE
        : status === "error"
          ? BROKEN_LINK_MESSAGE
          : status === "none"
            ? NO_LINK_MESSAGE
            : accessToken
              ? `Hi ${getUserName(accessToken)}! 👋`
              : "Hi! 👋";

    setMessages((prev) =>
      prev.length === 1 && prev[0].id === "welcome"
        ? [{ ...prev[0], content }]
        : prev,
    );
  }, [accessToken, status]);

  const [history, setHistory] =
  useState<ChatHistoryMessage[]>([]);

  // Returned by the server on the first turn and echoed back on every later one,
  // so the whole session lands in a single conversation rather than one per
  // message. The server verifies it belongs to this token before honouring it.
  const [conversationId, setConversationId] =
  useState<string | null>(null);

  const [usage, setUsage] = useState<Usage | null>(null);

  // The allowance, fetched once the session can authenticate. Spends nothing, so
  // the header can show "5 / 5 questions left" on arrival instead of staying
  // blank until the first answer comes back.
  useEffect(() => {
    if (status !== "ready" || !accessToken) {
      return;
    }

    let cancelled = false;

    sessionService
      .get(authFetch)
      .then((info) => {
        if (!cancelled) setUsage(info.usage);
      })
      .catch(() => {
        // Not worth surfacing: the count is a nicety, and any real problem with
        // the session shows up the moment a question is asked.
      });

    return () => {
      cancelled = true;
    };
  }, [status, accessToken, authFetch]);

  const [input, setInput] = useState("");

  const loading =
    messages.at(-1)?.status === "streaming";

  // Nothing to send with, so the composer stays shut rather than letting the
  // hirer type a question into a 401 — or into a 429, once the allowance is
  // known to be gone. The two are shut for different reasons and the placeholder
  // says which: "this link can't start a session" is the wrong thing to tell
  // someone whose session is fine and who has simply run out of questions.
  const outOfQuestions = usage?.remaining === 0;
  const disabled = status !== "ready" || outOfQuestions;

  const disabledReason = !disabled
    ? null
    : outOfQuestions
      ? "No questions left on this link"
      : "This link can't start a session";


  const addMessage = (message: Message) => {
    setMessages((prev) => [
      ...prev,
      message,
    ]);
  };


  const updateLastMessage = (
    updater: (message: Message) => Message
  ) => {
    setMessages((prev) => {
      if (prev.length === 0) {
        return prev;
      }

      const next = [...prev];

      next[next.length - 1] =
        updater(next[next.length - 1]);

      return next;
    });
  };


  const sendMessage = async (
  question?: string
) => {

  const text =
    typeof question === "string"
      ? question.trim()
      : input.trim();

    if (!text || loading || disabled) {
      return;
    }


    addMessage({
      id: crypto.randomUUID(),
      role: "user",
      content: text,
      createdAt: new Date(),
      status: "complete",
    });


    setInput("");


    try {

      // Create empty assistant message
      // that will receive streamed chunks
      addMessage({
        id: crypto.randomUUID(),
        role: "assistant",
        content: "",
        createdAt: new Date(),
        status: "streaming",
      });


      await chatService.stream(
  authFetch,
  {
    message: text,
    history,
    conversation_id: conversationId,
  },
  {
    onToken(value) {
      updateLastMessage((message) => ({
        ...message,
        content: message.content + value,
      }));
    },

    onDone(history, usage, newConversationId) {
      setHistory(history);
      setUsage(usage);
      if (newConversationId) {
        setConversationId(newConversationId);
      }

      updateLastMessage((message) => ({
        ...message,
        status: "complete",
      }));
    },

    onError(message) {
      console.error(message);
    },
  },
);


    } catch (error) {

      console.error(error);

      // A 429 means the allowance is gone; reflect that in the header too, so
      // the count and the message agree and the composer shuts.
      if (
        error instanceof ChatError &&
        error.status === 429
      ) {
        setUsage((prev) =>
          prev
            ? { ...prev, remaining: 0, used: prev.max }
            : prev,
        );
      }

      updateLastMessage((message) => ({
        ...message,
        content: failureMessage(error),
        status: "error",
      }));

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