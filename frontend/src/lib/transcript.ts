import type { Message } from "@/types/chat";

/**
 * The seeded greeting's id.
 *
 * Load-bearing rather than cosmetic: it is how the reducer recognises a
 * transcript nobody has added to yet, and therefore the only one it is still
 * allowed to rewrite.
 */
export const WELCOME_ID = "welcome";

/** What the greeting says, and whether it has anything to say yet. */
export type Greeting = Pick<
  Message,
  "content" | "status"
>;

export type TranscriptAction =
  /**
   * Seed *or* rewrite the greeting.
   *
   * One action because they are one decision made at two moments — the lazy
   * initialiser makes it against an empty transcript, and an effect makes it
   * again once a claim link has produced a token. Two actions would be two
   * places for the guard below to drift apart.
   */
  | { type: "greeting/set"; greeting: Greeting }
  | {
      type: "user/asked";
      id: string;
      content: string;
      at: Date;
    }
  | { type: "assistant/opened"; id: string; at: Date }
  | { type: "assistant/token"; value: string }
  | { type: "assistant/completed" }
  | { type: "assistant/failed"; content: string }
  /** Everything sessionStorage had, replacing what is here. */
  | {
      type: "transcript/restored";
      messages: Message[];
    };

/**
 * Rewrite the last message, or nothing if there isn't one.
 *
 * The `updateLastMessage` this replaces took a callback and was called from
 * four places with four different closures, which is how "what can happen to a
 * message" became a question you could only answer by reading the whole send
 * path. Here the four are the four action types above.
 */
function mapLast(
  messages: Message[],
  update: (message: Message) => Message,
): Message[] {
  const last = messages.at(-1);

  return last
    ? [...messages.slice(0, -1), update(last)]
    : messages;
}

export function transcriptReducer(
  messages: Message[],
  action: TranscriptAction,
): Message[] {
  switch (action.type) {
    case "greeting/set": {
      const [first, ...rest] = messages;

      // Seeding. `createdAt: new Date(0)` keeps the greeting first under any
      // ordering and makes it recognisable in storage.
      if (!first) {
        return [
          {
            id: WELCOME_ID,
            role: "assistant",
            createdAt: new Date(0),
            ...action.greeting,
          },
        ];
      }

      // Rewriting, and only while the greeting is still the only message —
      // once the hirer has asked something, the transcript is theirs.
      //
      // The greeting is spread whole, `status` included: one seeded as
      // "streaming" whose content alone was replaced would keep the typing
      // dots behind its own text forever.
      return rest.length === 0 &&
        first.id === WELCOME_ID
        ? [{ ...first, ...action.greeting }]
        : messages;
    }

    case "user/asked":
      return [
        ...messages,
        {
          id: action.id,
          role: "user",
          content: action.content,
          createdAt: action.at,
          status: "complete",
        },
      ];

    // An empty assistant message with `status: "streaming"` is what
    // MessageBubble draws as the typing dots, and what `loading` is derived
    // from. Opening it before the request goes out is what shuts the composer
    // for the duration of the turn.
    case "assistant/opened":
      return [
        ...messages,
        {
          id: action.id,
          role: "assistant",
          content: "",
          createdAt: action.at,
          status: "streaming",
        },
      ];

    case "assistant/token":
      return mapLast(messages, (message) => ({
        ...message,
        content: message.content + action.value,
      }));

    case "assistant/completed":
      return mapLast(messages, (message) => ({
        ...message,
        status: "complete",
      }));

    /**
     * The turn broke.
     *
     * Marking the bubble `error` is what unsticks the page: no `done` frame
     * follows a failure, so a bubble left `streaming` keeps `loading` true and
     * the composer shut, with no way back except a reload.
     */
    case "assistant/failed":
      return mapLast(messages, (message) => ({
        ...message,
        content: action.content,
        status: "error",
      }));

    // Wholesale, not merged: what is in storage is the whole transcript
    // including its greeting, and merging would leave the freshly seeded
    // greeting sitting above a restored copy of itself.
    case "transcript/restored":
      return action.messages;
  }
}

/**
 * The transcript on the very first render.
 *
 * Expressed as the reducer's own `greeting/set` against nothing, so "what a
 * seeded greeting looks like" has one definition rather than two that have to
 * be kept in agreement. Passed to `useReducer` as its lazy initialiser.
 */
export function initialTranscript(
  greeting: Greeting,
): Message[] {
  return transcriptReducer([], {
    type: "greeting/set",
    greeting,
  });
}
