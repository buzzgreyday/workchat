import type { ChatHistoryMessage, Usage } from "./chat";

/**
 * What the server may say a turn is doing. A list as well as a type, because
 * this is checked at the trust boundary: a code not listed here is dropped, so
 * the backend can add one before this frontend has words for it.
 */
export const PROGRESS_CODES = [
  "preprocessing",
  "composing",
  "knowledge_lookup",
] as const;

export type ProgressCode = (typeof PROGRESS_CODES)[number];

export type SSEEvent =
  | {
      type: "state" | "thought";
      code: ProgressCode;
    }
  | {
      type: "token";
      value: string;
    }
  | {
      type: "done";
      history: ChatHistoryMessage[];
      usage: Usage;
      // Sent back so the next turn can be attributed to the same conversation
      // server-side. Null when the server could not record the turn.
      conversation_id: string | null;
      // The server's signature on `history`. Sent back with it next turn: a
      // history without one the server recognises is dropped and the
      // conversation starts over, so the history cannot be anything the server
      // did not write.
      history_signature: string | null;
    }
  | {
      type: "error";
      message: string;
    };