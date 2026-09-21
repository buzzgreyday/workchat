import { expect, test } from "@playwright/test";

import {
  doneFrame,
  mockBackend,
  openChat,
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
