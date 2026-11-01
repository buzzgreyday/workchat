import { expect, test } from "@playwright/test";

import {
  doneFrame,
  mockBackend,
  openChat,
  replyWith,
} from "./backend";

async function ask(
  page: import("@playwright/test").Page,
  question: string,
) {
  const composer = page.getByLabel(
    "Your question",
  );

  await composer.fill(question);
  await composer.press("Enter");
}

test("a reply is streamed into the transcript", async ({
  page,
}) => {
  await mockBackend(page, {
    stream: [
      { type: "token", value: "Backend " },
      { type: "token", value: "work." },
      doneFrame({ reply: "Backend work." }),
    ],
  });

  await openChat(page);
  await ask(page, "What does he do?");

  await expect(
    page.getByText("Backend work."),
  ).toBeVisible();
  await expect(
    page.getByText("4 / 5 questions left"),
  ).toBeVisible();
});

/**
 * The regression this suite exists for.
 *
 * A failed turn sends an error frame and *no* done frame. The frontend used to
 * log it to the console and nothing else, which left the bubble streaming, and
 * because the composer is shut while a reply is streaming it stayed shut — the
 * page was unusable until it was reloaded, with nothing on screen saying why.
 */
test("a failed reply says so, and the composer recovers", async ({
  page,
}) => {
  await mockBackend(page, {
    stream: [
      {
        type: "error",
        message:
          "Something went wrong generating that reply. Please try again.",
      },
    ],
  });

  await openChat(page);
  await ask(page, "What does he do?");

  await expect(
    page.getByText(
      "Something went wrong generating that reply.",
    ),
  ).toBeVisible();

  // No done frame arrives, so nothing else clears the streaming state.
  await expect(
    page.getByLabel("Generating a reply"),
  ).toHaveCount(0);

  const composer = page.getByLabel(
    "Your question",
  );

  await expect(composer).toBeEnabled();
  await expect(
    page.getByLabel("Send question"),
  ).toBeEnabled();

  // And it genuinely works again, rather than merely looking enabled.
  await ask(page, "Try again?");
  await expect(
    page.getByText("Try again?"),
  ).toBeVisible();
});

test("the allowance is re-read after a failure, since the question was still spent", async ({
  page,
}) => {
  let sessionCalls = 0;

  await mockBackend(page, {
    stream: [
      { type: "error", message: "It broke." },
    ],
  });

  await page.route("**/session", (route) => {
    sessionCalls += 1;

    return route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        subject: "Ada Lovelace",
        version: 2,
        usage: {
          used: sessionCalls,
          remaining: 5 - sessionCalls,
          max: 5,
        },
        expires_at: new Date(
          Date.now() + 86_400_000,
        ).toISOString(),
        session_id: "session-1",
      }),
    });
  });

  await openChat(page);
  await expect(
    page.getByText("4 / 5 questions left"),
  ).toBeVisible();

  await ask(page, "What does he do?");

  // Usage only rides a done frame, so without a re-read the header would still
  // claim the question was never spent.
  await expect(
    page.getByText("3 / 5 questions left"),
  ).toBeVisible();
});

test("Shift+Enter writes a second line instead of sending", async ({
  page,
}) => {
  const requests: Array<Record<string, unknown>> =
    [];

  await mockBackend(page, { requests });

  await openChat(page);

  const composer = page.getByLabel(
    "Your question",
  );

  await composer.fill("First line");
  await composer.press("Shift+Enter");
  await composer.type("Second line");

  expect(requests).toHaveLength(0);
  await expect(composer).toHaveValue(
    "First line\nSecond line",
  );

  await composer.press("Enter");

  await expect
    .poll(() => requests.length)
    .toBe(1);
  expect(requests[0]?.message).toBe(
    "First line\nSecond line",
  );
});

const RETRY = /Try again/;

/** Answers each question from `answers`, and notes what each request carried. */
async function scriptedStream(
  page: import("@playwright/test").Page,
  answers: Array<(route: import("@playwright/test").Route) => Promise<void>>,
) {
  const sent: Array<{ key: string | undefined; message: unknown }> = [];

  // Added after mockBackend, so it is the one that answers.
  await page.route("**/chat/stream", (route) => {
    const request = route.request();

    if (request.method() !== "POST") {
      return route.fallback();
    }

    sent.push({
      key: request.headers()["x-idempotency-key"],
      message: request.postDataJSON().message,
    });

    const answer = answers[sent.length - 1];

    return answer ? answer(route) : route.abort();
  });

  return sent;
}

const answerWith =
  (...frames: Array<Record<string, unknown>>) =>
  (route: import("@playwright/test").Route) =>
    route.fulfill({
      contentType: "text/event-stream",
      body: frames
        .map((frame) => `data: ${JSON.stringify(frame)}\n\n`)
        .join(""),
    });

const finished = answerWith(
  { type: "token", value: "Backend work." },
  doneFrame({ reply: "Backend work." }),
);

const dropped = (route: import("@playwright/test").Route) => route.abort("connectionreset");

test("each question goes out once, with a key of its own", async ({
  page,
}) => {
  await mockBackend(page);
  const sent = await scriptedStream(page, [finished, finished]);

  await openChat(page);
  await ask(page, "First?");
  await expect(page.getByText("Backend work.")).toBeVisible();
  await ask(page, "Second?");

  await expect.poll(() => sent.length).toBe(2);
  expect(sent[0]?.key).toBeTruthy();
  expect(sent[1]?.key).toBeTruthy();
  expect(sent[1]?.key).not.toBe(sent[0]?.key);
});

test("two sends in one tick ask the question once", async ({
  page,
}) => {
  await mockBackend(page);
  const sent = await scriptedStream(page, [finished, finished]);

  await openChat(page);
  await page.getByLabel("Your question").fill("Once?");

  // In one task, so React has no chance to render between them: the guard that
  // reads `loading` would let both through.
  await page.getByLabel("Send question").evaluate((button: HTMLElement) => {
    button.click();
    button.click();
  });

  await expect(page.getByText("Backend work.")).toBeVisible();
  expect(sent).toHaveLength(1);
});

test("a dropped connection offers a retry of the same question under the same key", async ({
  page,
}) => {
  await mockBackend(page);
  const sent = await scriptedStream(page, [dropped, finished]);

  await openChat(page);
  await ask(page, "What does he do?");

  const retry = page.getByRole("button", { name: RETRY });

  await retry.click();

  await expect(page.getByText("Backend work.")).toBeVisible();
  await expect(retry).toHaveCount(0);
  expect(sent).toHaveLength(2);
  expect(sent[1]).toEqual(sent[0]);

  // The failure was replaced, not left above the answer, and the question is
  // on the page once.
  await expect(page.getByText("Something went wrong")).toHaveCount(0);
  await expect(page.getByText("What does he do?")).toHaveCount(1);
});

test("an error frame offers a retry too", async ({ page }) => {
  await mockBackend(page);
  const sent = await scriptedStream(page, [
    answerWith({ type: "error", message: "It broke." }),
    finished,
  ]);

  await openChat(page);
  await ask(page, "What does he do?");
  await page.getByRole("button", { name: RETRY }).click();

  await expect(page.getByText("Backend work.")).toBeVisible();
  expect(sent[1]?.key).toBe(sent[0]?.key);
});

test("a stream cut off with no result reopens the composer and offers a retry", async ({
  page,
}) => {
  await mockBackend(page);
  await scriptedStream(page, [
    answerWith({ type: "token", value: "Half an ans" }),
  ]);

  await openChat(page);
  await ask(page, "What does he do?");

  await expect(page.getByRole("button", { name: RETRY })).toBeVisible();
  await expect(page.getByLabel("Your question")).toBeEnabled();
});

test("a new question after a failure drops the retry and gets its own key", async ({
  page,
}) => {
  await mockBackend(page);
  const sent = await scriptedStream(page, [dropped, finished]);

  await openChat(page);
  await ask(page, "What does he do?");
  await expect(page.getByRole("button", { name: RETRY })).toBeVisible();

  await ask(page, "Something else?");

  await expect(page.getByText("Backend work.")).toBeVisible();
  await expect(page.getByRole("button", { name: RETRY })).toHaveCount(0);
  expect(sent[1]?.key).not.toBe(sent[0]?.key);
});

test("the last question can be retried with the composer shut", async ({
  page,
}) => {
  await mockBackend(page);

  // One left on arrival, none once the re-read after the failure comes back.
  let sessionCalls = 0;

  await page.route("**/session", (route) => {
    sessionCalls += 1;

    const used = sessionCalls === 1 ? 0 : 1;

    return route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        subject: "Ada Lovelace",
        version: 2,
        usage: { used, remaining: 1 - used, max: 1 },
        expires_at: new Date(Date.now() + 86_400_000).toISOString(),
        session_id: "session-1",
      }),
    });
  });

  const sent = await scriptedStream(page, [dropped, finished]);

  await openChat(page);
  await ask(page, "My last one?");

  await expect(page.getByLabel("Your question")).toBeDisabled();

  await page.getByRole("button", { name: RETRY }).click();

  await expect(page.getByText("Backend work.")).toBeVisible();
  expect(sent[1]).toEqual(sent[0]);
});

test("a question out of attempts says so and stops offering", async ({
  page,
}) => {
  await mockBackend(page);
  await scriptedStream(page, [
    dropped,
    (route) =>
      route.fulfill({
        status: 409,
        contentType: "application/json",
        body: JSON.stringify({
          detail: "This question has been retried too many times",
        }),
      }),
  ]);

  await openChat(page);
  await ask(page, "What does he do?");
  await page.getByRole("button", { name: RETRY }).click();

  await expect(page.getByText("as many times as I can")).toBeVisible();
  await expect(page.getByRole("button", { name: RETRY })).toHaveCount(0);
  await expect(page.getByLabel("Your question")).toBeEnabled();
});

/** How far the transcript is from showing its last line, in pixels. */
async function transcriptGap(
  page: import("@playwright/test").Page,
): Promise<number> {
  return page
    .getByRole("log", { name: "Conversation" })
    .evaluate(
      (el) =>
        el.scrollHeight -
        el.scrollTop -
        el.clientHeight,
    );
}

/**
 * Two ways the transcript used to be left behind.
 *
 * A reply taller than the follow threshold, arriving in one chunk, was read as
 * the reader having scrolled away — measured after it had landed, the reader
 * was suddenly a long way from the bottom — so following stopped with nobody
 * having touched anything. And a question asked while scrolled up stayed
 * scrolled up, sending the question and its answer below the fold.
 */
test("the transcript follows a long reply, and comes back down for a new question", async ({
  page,
}) => {
  await mockBackend(page, {
    stream: replyWith(
      "He has built backends in Python for a decade. ".repeat(80),
    ),
  });

  await openChat(page);
  await ask(page, "What does he do?");

  await expect(
    page.getByText("backends in Python").first(),
  ).toBeVisible();

  await expect
    .poll(() => transcriptGap(page))
    .toBeLessThanOrEqual(1);

  // Scroll away to re-read, and give the scroll event its frame to land —
  // it is dispatched on the next animation frame, not synchronously.
  await page
    .getByRole("log", { name: "Conversation" })
    .evaluate(async (el) => {
      el.scrollTop = 0;

      await new Promise((resolve) =>
        requestAnimationFrame(() =>
          requestAnimationFrame(resolve),
        ),
      );
    });

  expect(await transcriptGap(page)).toBeGreaterThan(120);

  await ask(page, "And before that?");

  // Not `toBeInViewport()` on the question itself. The mock answers every
  // question with the same reply, and one this long lands underneath it and
  // pushes it back off the top — which is the transcript following its newest
  // line, the very thing being asserted. That it came back down at all is what
  // the fault was about, and the gap below is what says so.
  await expect
    .poll(() => transcriptGap(page))
    .toBeLessThanOrEqual(1);
});
