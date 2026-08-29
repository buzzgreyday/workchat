import {
  ChatHistoryMessage,
  ChatRequest,
  ChatResponse,
  Usage,
} from "@/types/chat";
import { SSEEvent } from "@/types/sse";
import { AuthFetch } from "@/hooks/useSession";

/**
 * A failed chat request, with enough detail to say something true about it.
 *
 * The bare `Error("Server returned 429")` this replaces meant the UI could only
 * ever offer one apology for every failure, so a hirer who had simply used up
 * their questions was told something might have gone wrong.
 */
export class ChatError extends Error {
  readonly status: number;
  readonly detail: string;

  constructor(status: number, detail: string) {
    super(detail || `Server returned ${status}`);
    this.name = "ChatError";
    this.status = status;
    this.detail = detail;
  }
}

async function toError(
  response: Response,
): Promise<ChatError> {
  let detail = "";

  try {
    detail = (await response.json())?.detail ?? "";
  } catch {
    // A non-JSON body (a proxy error page, a dropped connection) leaves the
    // status to speak for itself.
  }

  return new ChatError(response.status, detail);
}

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
      throw await toError(response);
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
      throw await toError(response);
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