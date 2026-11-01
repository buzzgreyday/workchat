import type { ProgressCode } from "./sse";

export interface ChatHistoryMessage {
  role:
    | "user"
    | "assistant"
    | "tool";

  content: string;

  tool_call_id?: string;
}


export interface ChatRequest {
  message: string;
  history: ChatHistoryMessage[];
  // What the server signed `history` with when it handed it back. Required
  // with any history at all: unsigned, the server drops it.
  history_signature?: string | null;
  conversation_id?: string | null;
}


export interface Message {
  id: string;

  role:
    | "user"
    | "assistant";

  content: string;

  createdAt: Date;

  status:
    | "streaming"
    | "complete"
    | "error";

  // What a reply is waiting on, until its first word. Only ever set on a reply
  // to a question: a streaming bubble without it is the greeting's typing dots,
  // waiting on a session rather than an answer.
  progress?: MessageProgress;
}

/** The server's steps, and the one before it has answered at all. */
export type MessageProgress = ProgressCode | "sending";

export interface Usage {
    used: number,
    remaining: number,
    max: number
}