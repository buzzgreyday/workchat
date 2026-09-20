"use client";

import { ChatHistoryMessage, Message } from "@/types/chat";

/**
 * Keeping a conversation across a reload.
 *
 * `useSession` already goes to some trouble so F5 does not cost the hirer their
 * single-use link. Without this the session survived and the conversation did
 * not: the agent lost every turn of context, and the backend — handed a null
 * conversation id — opened a second row for the same person.
 *
 * `sessionStorage`, not `localStorage`: this is somebody's questions about
 * somebody's CV, and the right lifetime for that on a possibly shared machine
 * is the tab it was asked in.
 *
 * The access token is deliberately **not** here. It lives in memory precisely
 * so that script on the page cannot read it back, which is the whole reason the
 * refresh half is an httpOnly cookie. What survives a reload is the
 * conversation; the credential is re-derived from that cookie.
 */

const KEY = "workchat:conversation";

interface Stored {
  // The grant this transcript belongs to. A different link opened in the same
  // tab must not be shown the previous hirer's questions.
  grantId: string;
  conversationId: string | null;
  history: ChatHistoryMessage[];
  messages: Array<
    Omit<Message, "createdAt"> & {
      createdAt: string;
    }
  >;
}

export interface Conversation {
  conversationId: string | null;
  history: ChatHistoryMessage[];
  messages: Message[];
}

export function loadConversation(
  grantId: string,
): Conversation | null {
  if (typeof window === "undefined" || !grantId) {
    return null;
  }

  try {
    const raw =
      window.sessionStorage.getItem(KEY);

    if (!raw) {
      return null;
    }

    const stored: Stored = JSON.parse(raw);

    if (stored.grantId !== grantId) {
      return null;
    }

    return {
      conversationId: stored.conversationId,
      history: stored.history,
      // Dates do not survive JSON. Left as strings they reach a component
      // expecting a Date, which is a crash on the first render after a reload.
      messages: stored.messages.map(
        (message) => ({
          ...message,
          createdAt: new Date(message.createdAt),
        }),
      ),
    };
  } catch {
    // Unparseable, or storage unavailable in this context. A lost transcript
    // is a worse first impression than none, but not worth a broken page.
    return null;
  }
}

export function saveConversation(
  grantId: string,
  conversation: Conversation,
): void {
  if (typeof window === "undefined" || !grantId) {
    return;
  }

  try {
    const stored: Stored = {
      grantId,
      conversationId:
        conversation.conversationId,
      history: conversation.history,
      messages: conversation.messages.map(
        (message) => ({
          ...message,
          createdAt:
            message.createdAt.toISOString(),
        }),
      ),
    };

    window.sessionStorage.setItem(
      KEY,
      JSON.stringify(stored),
    );
  } catch {
    // Private browsing, a full quota, storage disabled. Persistence is a
    // convenience and must never cost the hirer the answer on screen.
  }
}
