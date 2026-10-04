import { expect, test } from "@playwright/test";

import {
  mockBackend,
  openChat,
  replyWith,
  waitForReady,
} from "./backend";

/**
 * What the composer holds to, and what it carries between turns.
 *
 * The limit is the server's (MAX_MESSAGE_CHARS); the composer mirrors it so a
 * question stops at the limit rather than being refused once sent.
 */

test("a question stops at 150 characters, and says how close it is", async ({
  page,
}) => {
  await mockBackend(page);
  await openChat(page);
  await waitForReady(page);

  const composer = page.getByLabel("Your question");

  await composer.fill("x".repeat(200));
  await expect(composer).toHaveValue("x".repeat(150));
  await expect(page.getByText("150 / 150")).toBeVisible();

  await composer.fill("Hi");
  await expect(page.getByText("2 / 150")).toBeVisible();

  // An empty composer stays a quiet one.
  await composer.fill("");
  await expect(page.getByText("/ 150")).toHaveCount(0);
});

test("a question refused as too long is explained, not called a failure", async ({
  page,
}) => {
  await mockBackend(page);
  await page.route("**/chat/stream", (route) =>
    route.fulfill({
      status: 422,
      contentType: "application/json",
      body: JSON.stringify({ detail: [] }),
    }),
  );

  await openChat(page);
  await waitForReady(page);

  await page.getByLabel("Your question").fill("Too long, says the server");
  await page.getByLabel("Your question").press("Enter");

  await expect(
    page.getByText("keep questions to 150 characters"),
  ).toBeVisible();
});

test("the history goes back with the signature the server put on it", async ({
  page,
}) => {
  const requests: Array<Record<string, unknown>> = [];

  await mockBackend(page, {
    requests,
    stream: replyWith("First answer.", { conversationId: "c-1" }),
  });

  await openChat(page);
  await waitForReady(page);

  const composer = page.getByLabel("Your question");

  await composer.fill("First?");
  await composer.press("Enter");
  await expect(page.getByText("First answer.")).toBeVisible();

  await composer.fill("Second?");
  await composer.press("Enter");

  await expect.poll(() => requests.length).toBe(2);
  expect(requests[0]?.history_signature ?? null).toBeNull();
  expect(requests[1]?.history_signature).toBe("signed:c-1");
  expect(requests[1]?.history).toEqual([
    { role: "assistant", content: "First answer." },
  ]);
});
