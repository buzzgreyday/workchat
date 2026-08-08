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
    }
  | {
      type: "error";
      message: string;
    };