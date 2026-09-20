import { Page, Route } from "@playwright/test";

/**
 * A backend, as far as the browser can tell.
 *
 * Every route the chat page talks to, fulfilled from the test rather than a
 * server. Lets a test ask for the states that matter and are otherwise hard to
 * produce on demand — a reply that fails mid-stream, a claim link already
 * spent, an allowance down to its last question.
 */

/**
 * A token the page can decode.
 *
 * `jwt-decode` only base64-decodes; it never verifies, so a made-up signature
 * is enough and no signing key has to exist in the test suite. The claims that
 * matter here are `sub`, which becomes the greeting, and `tid`, which keys the
 * stored conversation.
 */
export function fakeToken({
  sub = "Ada Lovelace",
  grantId = "grant-1",
}: {
  sub?: string;
  grantId?: string;
} = {}): string {
  const encode = (value: object) =>
    Buffer.from(JSON.stringify(value))
      .toString("base64url");

  const header = encode({
    alg: "HS256",
    typ: "JWT",
  });

  const payload = encode({
    sub,
    tid: grantId,
    ver: 2,
    typ: "access",
    sid: "session-1",
    exp: Math.floor(Date.now() / 1000) + 900,
  });

  return `${header}.${payload}.not-a-real-signature`;
}

export function sse(
  ...frames: object[]
): string {
  // Two newlines between frames: that is the boundary the reader splits on.
  return (
    frames
      .map(
        (frame) =>
          `data: ${JSON.stringify(frame)}`,
      )
      .join("\n\n") + "\n\n"
  );
}

export const doneFrame = ({
  reply = "Backend work, mostly Python.",
  conversationId = "conversation-1",
  remaining = 4,
  max = 5,
}: {
  reply?: string;
  conversationId?: string;
  remaining?: number;
  max?: number;
} = {}) => ({
  type: "done",
  reply,
  history: [
    { role: "assistant", content: reply },
  ],
  usage: { used: max - remaining, remaining, max },
  conversation_id: conversationId,
});

/**
 * A whole answer: the text as a token frame, then the terminal frame.
 *
 * Both halves are needed. The bubble is filled by `token` frames as they
 * arrive; `done` carries the transcript and the allowance but never the text,
 * so a mock that sends only `done` renders an empty reply.
 */
export function replyWith(
  reply: string,
  options: {
    conversationId?: string;
    remaining?: number;
    max?: number;
  } = {},
): object[] {
  return [
    { type: "token", value: reply },
    doneFrame({ reply, ...options }),
  ];
}

export interface BackendOptions {
  sub?: string;
  grantId?: string;
  remaining?: number;
  max?: number;
  /** Frames the next /chat/stream answers with. */
  stream?: object[];
  /** Bodies sent to /chat/stream, in order, for assertions. */
  requests?: Array<Record<string, unknown>>;
}

export async function mockBackend(
  page: Page,
  options: BackendOptions = {},
): Promise<void> {
  const {
    sub = "Ada Lovelace",
    grantId = "grant-1",
    remaining = 5,
    max = 5,
    stream,
    requests,
  } = options;

  const token = fakeToken({ sub, grantId });

  const session = (route: Route) =>
    route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        access_token: token,
        token_type: "bearer",
        expires_in: 900,
        refresh_expires_in: 604800,
      }),
    });

  await page.route(
    "**/v2/auth/claim",
    session,
  );
  await page.route(
    "**/v2/auth/refresh",
    session,
  );

  await page.route("**/session", (route) =>
    route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        subject: sub,
        version: 2,
        usage: {
          used: max - remaining,
          remaining,
          max,
        },
        expires_at: new Date(
          Date.now() + 86_400_000,
        ).toISOString(),
        session_id: "session-1",
      }),
    }),
  );

  await page.route(
    "**/chat/stream",
    (route) => {
      requests?.push(
        JSON.parse(
          route.request().postData() ?? "{}",
        ),
      );

      return route.fulfill({
        contentType: "text/event-stream",
        body: sse(
          ...(stream ??
            replyWith(
              "Backend work, mostly Python.",
            )),
        ),
      });
    },
  );
}
