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

/**
 * A genuinely v1-shaped token: `jti`, and no `ver`.
 *
 * Deliberately separate from `fakeToken`. That one mints the *v2* access token
 * the mocked `/v2/auth` routes hand back — and handing it in as `?token=`,
 * which is what every spec used to do, meant the suite never once saw a real
 * v1 claim set. `getGrantId`'s `claims.jti` fallback (src/lib/auth.ts) has
 * therefore never run in a test, despite eighteen of them calling themselves
 * v1.
 */
export function legacyToken({
  sub = "Ada Lovelace",
  grantId = "legacy-grant-1",
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

  // No `ver`, no `tid`, no `sid`: the absence of `ver` is precisely what marks
  // a token as v1, and `jti` is both the token id and the grant.
  const payload = encode({
    sub,
    jti: grantId,
    exp:
      Math.floor(Date.now() / 1000) + 604_800,
  });

  return `${header}.${payload}.not-a-real-signature`;
}

/**
 * A promise a route can wait on, so a state that is normally a race becomes
 * something a test can stand still and look at.
 */
export function gate(): {
  held: Promise<void>;
  release: () => void;
} {
  let release: () => void = () => {};

  const held = new Promise<void>((resolve) => {
    release = resolve;
  });

  return { held, release };
}

/**
 * How many times each auth route was called.
 *
 * Several things worth asserting are invisible on screen — that a v1 link
 * never attempts an exchange, that one 401 causes exactly one refresh, that a
 * 409 is retried once. Counting is the only way to see them.
 */
export interface AuthCalls {
  claim: number;
  refresh: number;
}

export function authCalls(): AuthCalls {
  return { claim: 0, refresh: 0 };
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

/** How `/v2/auth/claim` answers. */
export type ClaimBehaviour =
  // Exchanged for a session.
  | "ok"
  // Single use, and this is the second. 409 — only a new link helps.
  | "spent"
  // Anything else that means no session came back.
  | "error";

/** How `/v2/auth/refresh` answers. */
export type RefreshBehaviour =
  | "ok"
  // No cookie, or a dead one: there is no way back in from here.
  | "gone"
  // Another tab rotated first. The client is expected to retry once and win.
  | "conflictOnce";

export interface BackendOptions {
  sub?: string;
  grantId?: string;
  remaining?: number;
  max?: number;
  /** Frames the next /chat/stream answers with. */
  stream?: object[];
  /** Bodies sent to /chat/stream, in order, for assertions. */
  requests?: Array<Record<string, unknown>>;
  /** Default "ok". The failing shapes are what reach `spent` and `error`. */
  claim?: ClaimBehaviour;
  /** Default "ok". "gone" is what a visitor with no link at all sees. */
  refresh?: RefreshBehaviour;
  /** Awaited before the claim is fulfilled, to hold the loading state open. */
  holdClaim?: Promise<void>;
  /**
   * Awaited before /chat/stream answers, so a test can put the page in a known
   * state between the question going out and the reply coming back.
   */
  holdStream?: Promise<void>;
  /** Bumped per auth call, for the assertions no screen can show. */
  calls?: AuthCalls;
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
    claim = "ok",
    refresh = "ok",
    holdClaim,
    holdStream,
    calls,
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

  /** The domain error shape the backend's exception handler produces. */
  const refuse = (
    route: Route,
    status: number,
    detail: string,
  ) =>
    route.fulfill({
      status,
      contentType: "application/json",
      body: JSON.stringify({ detail }),
    });

  await page.route(
    "**/v2/auth/claim",
    async (route) => {
      if (calls) {
        calls.claim += 1;
      }

      // Held open so a test can watch the page while the exchange is still in
      // flight — the window the greeting used to get wrong.
      if (holdClaim) {
        await holdClaim;
      }

      if (claim === "spent") {
        return refuse(
          route,
          409,
          "This link has already been used. Ask for a new one.",
        );
      }

      if (claim === "error") {
        return refuse(
          route,
          500,
          "Internal server error",
        );
      }

      return session(route);
    },
  );

  await page.route(
    "**/v2/auth/refresh",
    (route) => {
      const attempt = calls
        ? (calls.refresh += 1)
        : 1;

      if (refresh === "gone") {
        return refuse(
          route,
          401,
          "Missing refresh token",
        );
      }

      // One 409 then success: another tab rotated first, which the client is
      // expected to absorb with a single retry rather than treat as a replay.
      if (
        refresh === "conflictOnce" &&
        attempt === 1
      ) {
        return refuse(
          route,
          409,
          "Rotation in progress",
        );
      }

      return session(route);
    },
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
    async (route) => {
      requests?.push(
        JSON.parse(
          route.request().postData() ?? "{}",
        ),
      );

      if (holdStream) {
        await holdStream;
      }

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

/** The claim token a v2 link carries, unless a test needs a second one. */
export const CLAIM = "a-claim-token";

/**
 * Open the page the way a hirer actually does.
 *
 * `?claim=` — the link carries a single-use claim token, which the page
 * exchanges for an access token held in memory plus a refresh cookie it cannot
 * read. The whole suite used to open `?token=` instead, putting the access
 * token itself in the URL: the v1 shape, which is being retired precisely
 * because a URL is copied into histories, referrers and logs.
 */
export async function openChat(
  page: Page,
  { claim = CLAIM }: { claim?: string } = {},
): Promise<void> {
  await page.goto(
    `/?claim=${encodeURIComponent(claim)}`,
  );
}

/**
 * Open a legacy v1 link. Only `legacy.spec.ts` should reach for this.
 */
export async function openLegacyChat(
  page: Page,
  token: { sub?: string; grantId?: string } = {},
): Promise<void> {
  await page.goto(
    `/?token=${legacyToken(token)}`,
  );
}

/**
 * Wait until the session is open.
 *
 * A v1 link was the access token, so the page was usable on its first paint.
 * A claim link is one round trip short of that, and a spec that means "once
 * the session is open" should say so rather than lean on Playwright's
 * actionability timeout to paper over the difference.
 */
export async function waitForReady(
  page: Page,
): Promise<void> {
  await page
    .getByLabel("Your question")
    .and(page.locator(":not([disabled])"))
    .waitFor({ state: "visible" });
}
