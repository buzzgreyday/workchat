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
  conversation_id?: string | null;
}


export interface ChatResponse {
  reply: string;
  history: ChatHistoryMessage[];
  usage: Usage;
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