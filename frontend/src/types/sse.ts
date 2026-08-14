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
    }
  | {
      type: "error";
      message: string;
    };