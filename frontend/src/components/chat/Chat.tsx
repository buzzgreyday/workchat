"use client";

import { useEffect } from "react";

import ChatHeader from "./Header";
import MessageList from "./MessageList";
import ChatInput from "./Input";

import { useChat } from "@/hooks/useChat";

export default function Chat({ token }: { token: string }) {
  // Drop the token from the address bar / history once it's been read, so it
  // doesn't linger in browser history or get logged in server access logs.
  useEffect(() => {
    if (token && window.location.search.includes("token=")) {
      window.history.replaceState({}, "", window.location.pathname);
    }
  }, [token]);

  const {
    messages,
    input,
    loading,
    usage,
    setInput,
    sendMessage,
  } = useChat(token);

  return (
    <div className="chat-card flex h-[calc(100dvh-2rem)] max-h-175 w-full max-w-4xl flex-col overflow-hidden rounded-3xl shadow-2xl">
      <ChatHeader usage={usage} />

      <MessageList messages={messages} />

      <ChatInput
        value={input}
        loading={loading}
        onChange={setInput}
        onSend={sendMessage}
      />
    </div>
  );
}