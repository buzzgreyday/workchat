"use client";

import {
  useEffect,
  useReducer,
  useRef,
  type Dispatch,
} from "react";

import {
  loadConversation,
  saveConversation,
} from "@/lib/conversation";
import type { TranscriptAction } from "@/lib/transcript";
import type {
  ChatHistoryMessage,
  Message,
} from "@/types/chat";

/**
 * The model's view of the conversation.
 *
 * Not the same list as the transcript: `history` is what the agent is handed
 * as context and `messages` is what the reader sees. They are written together
 * and restored together, which is why they live behind one reducer rather than
 * two `useState`s that have to be kept in step by whoever remembers to.
 */
interface Memory {
  history: ChatHistoryMessage[];
  // Returned by the server on the first turn and echoed back on every later
  // one, so the whole session lands in a single conversation rather than one
  // per message. The server verifies it belongs to this token before
  // honouring it.
  conversationId: string | null;
}

type MemoryAction = {
  type: "remembered";
  memory: Memory;
};

// The previous value is unread because the only action there is replaces it
// wholesale — a turn settles with a whole history and a whole conversation id,
// never with a patch. Underscored rather than dropped so the signature still
// reads as a reducer, and so an action that *does* need the previous value has
// somewhere obvious to find it.
function memoryReducer(
  _memory: Memory,
  action: MemoryAction,
): Memory {
  switch (action.type) {
    case "remembered":
      return action.memory;
  }
}

const EMPTY: Memory = {
  history: [],
  conversationId: null,
};

export function useConversationMemory({
  grantId,
  messages,
  dispatch,
  // False while a reply is streaming.
  settled,
}: {
  grantId: string;
  messages: Message[];
  dispatch: Dispatch<TranscriptAction>;
  settled: boolean;
}) {
  const [memory, remember] = useReducer(
    memoryReducer,
    EMPTY,
  );

  // Restored in an effect rather than in a reducer's initialiser, and that is
  // not a style choice: sessionStorage does not exist while the server
  // renders, so seeding from it would make the first client render disagree
  // with the HTML and fail hydration.
  const restored = useRef(false);

  useEffect(() => {
    if (restored.current || !grantId) {
      return;
    }

    restored.current = true;

    const saved = loadConversation(grantId);

    if (!saved || saved.messages.length === 0) {
      return;
    }

    // Two dispatches and no `setState`: the transcript and the memory are
    // separate stores because they are read by different parts of the screen,
    // but each is restored in one go rather than field by field.
    dispatch({
      type: "transcript/restored",
      messages: saved.messages,
    });

    remember({
      type: "remembered",
      memory: {
        history: saved.history,
        conversationId: saved.conversationId,
      },
    });
  }, [grantId, dispatch]);

  // Written when a turn settles rather than as it streams: keying this on
  // `settled` means one write per answer instead of one per token, and the
  // thing worth keeping is the finished turn anyway. `history` stays empty
  // until the first reply lands, which is what keeps the bare greeting out of
  // storage.
  useEffect(() => {
    if (
      !grantId ||
      !settled ||
      memory.history.length === 0
    ) {
      return;
    }

    saveConversation(grantId, {
      conversationId: memory.conversationId,
      history: memory.history,
      messages,
    });
  }, [grantId, settled, messages, memory]);

  return { memory, remember };
}
