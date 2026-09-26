"use client";

import {
  createContext,
  use,
  useEffect,
  useRef,
  type ReactNode,
} from "react";

import { useChat } from "@/hooks/useChat";
import { useSession } from "@/hooks/useSession";
import { useViewportHeight } from "@/hooks/useViewportHeight";
import type { Owner } from "@/lib/owner";
import type { Message, Usage } from "@/types/chat";

/**
 * The part of the owner the chat itself shows: the name in its header.
 *
 * The profile links are the standalone page's (see `OwnerLinks`), so an
 * embedding page has nothing to pass for them.
 */
export type ChatOwner = Pick<Owner, "name">;

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
  owner: ChatOwner;
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
  seedQuestion,
  onUsageChange,
  ownsViewport,
  children,
}: {
  token?: string;
  claim?: string;
  owner: ChatOwner;
  /** A question to open the composer with, rather than an empty one. */
  seedQuestion?: string;
  /**
   * Told when the allowance moves. Nothing in this app listens; it exists for
   * the embed, where the host page owns everything around the chat and the
   * remaining questions are the one number it might want to show there.
   */
  onUsageChange?: (usage: Usage) => void;
  /**
   * False when the chat is a component of somebody else's page rather than the
   * page itself. Only the embed passes it.
   */
  ownsViewport?: boolean;
  children: ReactNode;
}) {
  // Publishes `--app-height`. Here because this is already where the page's
  // browser-side concerns live, and because it mounts once, unconditionally,
  // for the whole life of the page — including the spent and error states,
  // where the card is still on screen and still has to fit.
  //
  // Called unconditionally and told whether to act, rather than called
  // conditionally: that is the rule, and the embed needs it inert, not absent.
  useViewportHeight(ownsViewport);

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
  } = useChat({ ...session, seedQuestion });

  // Held in a ref and notified from an effect, not called where usage is set.
  // The embed passes a fresh arrow on every attribute change, so a plain
  // dependency would re-fire the notification on renders where the number did
  // not move — and the host is listening for changes, not for renders.
  const notify = useRef(onUsageChange);

  useEffect(() => {
    notify.current = onUsageChange;
  }, [onUsageChange]);

  useEffect(() => {
    if (usage) {
      notify.current?.(usage);
    }
  }, [usage]);

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
