import {
  ChatHistoryMessage,
  ChatRequest,
  ChatResponse,
  Usage,
} from "@/types/chat";
import { SSEEvent } from "@/types/sse";
import { AuthFetch } from "@/hooks/useSession";

const API_URL =
  process.env.NEXT_PUBLIC_API_URL ??
  "http://localhost:8000";

// Takes an authFetch rather than a bearer string because with v2 the right
// token is not knowable at call time: the one held when a request starts may
// have expired by the time it lands, and authFetch is what refreshes and
// retries. A v1 caller passes one that only ever attaches the same token.
class ChatService {
  async send(
    authFetch: AuthFetch,
    request: ChatRequest,
  ): Promise<ChatResponse> {
    const response = await authFetch(
      `${API_URL}/chat`,
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(request),
      },
    );

    if (!response.ok) {
      throw new Error(
        `Server returned ${response.status}`,
      );
    }

    return response.json();
  }

  async stream(
    authFetch: AuthFetch,
    request: ChatRequest,
    callbacks: {
      onToken: (value: string) => void;
      onDone: (
        history: ChatHistoryMessage[],
        usage: Usage,
        conversationId: string | null,
      ) => void;
      onError?: (message: string) => void;
    },
  ): Promise<void> {
    const response = await authFetch(
      `${API_URL}/chat/stream`,
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(request),
      },
    );

    if (!response.ok) {
      throw new Error(
        `Server returned ${response.status}`,
      );
    }

    if (!response.body) {
      throw new Error("No response body");
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();

    let buffer = "";

    while (true) {
      const { value, done } =
        await reader.read();

      if (done) {
        break;
      }

      buffer += decoder.decode(value, {
        stream: true,
      });

      const events = buffer.split("\n\n");
      buffer = events.pop() ?? "";

      for (const raw of events) {
        if (!raw.startsWith("data:")) {
          continue;
        }

        const json = raw.replace(
          /^data:\s*/,
          "",
        );

        const event =
          JSON.parse(json) as SSEEvent;

        switch (event.type) {
          case "token":
            callbacks.onToken(event.value);
            break;

          case "done":
            callbacks.onDone(
              event.history,
              event.usage,
              event.conversation_id ?? null,
            );
            break;

          case "error":
            callbacks.onError?.(
              event.message,
            );
            break;
        }
      }
    }
  }
}

export const chatService = new ChatService();