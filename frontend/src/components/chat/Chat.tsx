"use client";

import ChatHeader from "./Header";
import MessageList from "./MessageList";
import ChatInput from "./Input";

import { useChat } from "@/hooks/useChat";
import { useSession } from "@/hooks/useSession";

export default function Chat({
  token,
  claim,
}: {
  token?: string;
  claim?: string;
}) {
  // Owns the access token and, for a claim link, the one-shot exchange that
  // produces it. Dropping the credential out of the address bar happens in
  // there too — after the exchange settles, so a reload before it lands can
  // still retry rather than finding an empty URL.
  const session = useSession({ token, claim });

  const {
    messages,
    input,
    loading,
    disabled,
    disabledReason,
    usage,
    setInput,
    sendMessage,
  } = useChat(session);

  return (
    <div className="chat-card flex h-[calc(100dvh-2rem)] max-h-175 w-full max-w-4xl flex-col overflow-hidden rounded-3xl shadow-2xl">
      <ChatHeader usage={usage} />

      <MessageList messages={messages} />

      <ChatInput
        value={input}
        loading={loading}
        disabled={disabled}
        disabledReason={disabledReason}
        onChange={setInput}
        onSend={sendMessage}
      />
    </div>
  );
}
