import type { ChatHistoryMessage, Usage } from "./chat";


export type SSEEvent =
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