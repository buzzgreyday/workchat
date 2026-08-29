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
  // Seconds to wait, when the response said. Only the rate limiter sets it.
  readonly retryAfter: number | null;

  constructor(
    status: number,
    detail: string,
    retryAfter: number | null = null,
  ) {
    super(detail || `Server returned ${status}`);
    this.name = "ChatError";
    this.status = status;
    this.detail = detail;
    this.retryAfter = retryAfter;
  }
}

/**
 * The status alone is not enough to know what happened.
 *
 * Two very different things answer 429: the backend refusing a question because
 * the grant's allowance is spent, and Caddy refusing it because requests arrived
 * too fast. The first is a dead end and the second clears on its own, so the
 * detail — which only the backend sets — is what tells them apart.
 */
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

  const header = response.headers.get(
    "Retry-After",
  );
  const seconds = header
    ? Number.parseInt(header, 10)
    : NaN;

  return new ChatError(
    response.status,
    detail,
    Number.isFinite(seconds) && seconds > 0
      ? seconds
      : null,
  );
}

const API_URL =
  process.env.NEXT_PUBLIC_API_URL ??
  "http://localhost:8000";

// Takes an authFetch rather than a bearer string because with v2 the right
// token is not knowable at call time: the one held when a request starts may
// have expired by the time it lands, and authFetch is what refreshes and
// retries. A v1 caller passes one that only ever attaches the same token.
/**
 * Parse one SSE frame into a known event, or nothing.
 *
 * This is a trust boundary, and `JSON.parse(...) as SSEEvent` — which is what
 * used to be here — asserts a shape without checking a single field of it.
 * TypeScript cannot see through an assertion however strict it is set, so a
 * server change or a truncated frame would have surfaced as an undefined
 * property somewhere further along, not here.
 */
function toSSEEvent(json: string): SSEEvent | null {
  let raw: unknown;

  try {
    raw = JSON.parse(json);
  } catch {
    return null;
  }

  if (
    typeof raw !== "object" ||
    raw === null
  ) {
    return null;
  }

  const event = raw as Record<string, unknown>;

  switch (event.type) {
    case "token":
      return typeof event.value === "string"
        ? { type: "token", value: event.value }
        : null;

    case "done":
      return Array.isArray(event.history) &&
        typeof event.usage === "object" &&
        event.usage !== null
        ? {
            type: "done",
            history:
              event.history as ChatHistoryMessage[],
            usage: event.usage as Usage,
            conversation_id:
              typeof event.conversation_id ===
              "string"
                ? event.conversation_id
                : null,
          }
        : null;

    case "error":
      return typeof event.message === "string"
        ? { type: "error", message: event.message }
        : null;

    default:
      return null;
  }
}

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

        const event = toSSEEvent(json);

        // A frame we cannot make sense of is skipped rather than thrown: the
        // rest of the stream is still carrying the hirer's answer, and losing
        // the whole reply over one bad frame would be the worse failure.
        if (!event) {
          continue;
        }

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