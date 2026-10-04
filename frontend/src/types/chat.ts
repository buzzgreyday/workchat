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
}

export interface Usage {
    used: number,
    remaining: number,
    max: number
}