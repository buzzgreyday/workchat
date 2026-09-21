"use client";

import {
  createContext,
  use,
  type ReactNode,
} from "react";

import { useChat } from "@/hooks/useChat";
import { useSession } from "@/hooks/useSession";
import { useViewportHeight } from "@/hooks/useViewportHeight";
import type { Owner } from "@/lib/owner";
import type { Message, Usage } from "@/types/chat";

/**
 * What the transcript is, on its own.
 *
 * Split from the rest deliberately. This changes on *every streamed token*,
 * and one combined context would re-render the header and the composer once
 * per token for the length of every reply — strictly worse than the
 * prop-drilling it replaced. Two contexts means only the message list pays.
 */
interface TranscriptValue {
  messages: Message[];
}

/** Everything else: the composer, the allowance, and whose CV this is. */
interface ControlsValue {
  /**
   * Whose CV this is.
   *
   * Read on the server in page.tsx and handed across the boundary as a prop,
   * because a prop is the only thing that can cross it. What must not happen
   * is a client module importing `@/lib/owner`: it reads the environment at
   * request time, and the import would pull it into the browser bundle where
   * the value would be frozen at build.
   */
  owner: Owner;
  usage: Usage | null;
  input: string;
  loading: boolean;
  disabled: boolean;
  disabledReason: string | null;
  setInput: (value: string) => void;
  sendMessage: (question?: string) => void;
}

// `null` rather than a plausible-looking default. A default would let a
// component render outside the provider and quietly show an empty transcript
// for ever; this makes that a crash, on the first render, in development.
const TranscriptContext =
  createContext<TranscriptValue | null>(null);

const ControlsContext =
  createContext<ControlsValue | null>(null);

export function useTranscriptContext(): TranscriptValue {
  // React 19's `use`, which reads a context exactly as `useContext` did and is
  // the form this version documents.
  const value = use(TranscriptContext);

  if (!value) {
    throw new Error(
      "useTranscriptContext must be used inside <ChatProvider>",
    );
  }

  return value;
}

export function useControls(): ControlsValue {
  const value = use(ControlsContext);

  if (!value) {
    throw new Error(
      "useControls must be used inside <ChatProvider>",
    );
  }

  return value;
}

export function ChatProvider({
  token,
  claim,
  owner,
  children,
}: {
  token?: string;
  claim?: string;
  owner: Owner;
  children: ReactNode;
}) {
  // Publishes `--app-height`. Here because this is already where the page's
  // browser-side concerns live, and because it mounts once, unconditionally,
  // for the whole life of the page — including the spent and error states,
  // where the card is still on screen and still has to fit.
  useViewportHeight();

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

  // React 19: the context *is* the provider — no `.Provider`.
  return (
    <ControlsContext
      value={{
        owner,
        usage,
        input,
        loading,
        disabled,
        disabledReason,
        setInput,
        sendMessage,
      }}
    >
      <TranscriptContext value={{ messages }}>
        {children}
      </TranscriptContext>
    </ControlsContext>
  );
}
