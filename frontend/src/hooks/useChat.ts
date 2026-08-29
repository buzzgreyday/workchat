"use client";

import { useEffect, useState } from "react";

import { chatService } from "@/services/chat.service";
import { getUserName } from "@/lib/auth";
import { Message, ChatHistoryMessage, Usage } from "@/types/chat";
import { AuthFetch, SessionStatus } from "@/hooks/useSession";

const SPENT_LINK_MESSAGE =
  "This chat link has already been used, so I can't start a new session with it. " +
  "Links are single use — ask for a fresh one and I'll pick up from there.";

const BROKEN_LINK_MESSAGE =
  "I couldn't open a session from this link. It may have expired. " +
  "Ask for a fresh one and we can get started.";

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

  const [input, setInput] = useState("");

  const loading =
    messages.at(-1)?.status === "streaming";

  // Nothing to send with, so the composer stays shut rather than letting the
  // hirer type a question into a 401.
  const disabled = status !== "ready";


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


      updateLastMessage((message) => ({
        ...message,
        content:
          "Oops, either your token has reached it's limits or something went wrong. This project is still being developed.",
        status: "error",
      }));

    }
  };


  return {
    messages,
    input,
    loading,
    disabled,
    usage,

    setInput,
    sendMessage,
  };
}