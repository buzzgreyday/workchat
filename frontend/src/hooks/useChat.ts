"use client";

import { useState } from "react";

import { chatService } from "@/services/chat.service";
import { getUserName } from "@/lib/auth";
import { Message, ChatHistoryMessage, Usage } from "@/types/chat";

export function useChat(token: string) {
  const user = getUserName(token);

  const [messages, setMessages] = useState<Message[]>([
    {
      id: "welcome",
      role: "assistant",
      content: `Hi ${user}! 👋`,
      createdAt: new Date(0),
      status: "complete",
    },
  ]);

  const [history, setHistory] =
  useState<ChatHistoryMessage[]>([]);

  const [usage, setUsage] = useState<Usage | null>(null);

  const [input, setInput] = useState("");

  const loading =
    messages.at(-1)?.status === "streaming";


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

    if (!text || loading) {
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
  token,
  {
    message: text,
    history,
  },
  {
    onToken(value) {
      updateLastMessage((message) => ({
        ...message,
        content: message.content + value,
      }));
    },

    onDone(history, usage) {
      setHistory(history);
      setUsage(usage);

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
    usage,

    setInput,
    sendMessage,
  };
}