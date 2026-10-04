import { expect, test } from "@playwright/test";

import {
  authCalls,
  mockBackend,
  waitForReady,
} from "./backend";

/**
 * A guest trial: someone with no link is offered a few questions, earned by
 * a proof-of-work the page solves on its own.
 *
 * The challenge here is real — `sha256(salt + n)`, solved by the page's
 * worker exactly as in production — only small. What the mock skips is the
 * server's checking of it, which the backend's own tests cover.
 */

test("with no link and trials on, the chat offers one instead of a dead end", async ({
  page,
}) => {
  await mockBackend(page, { refresh: "gone", trial: "ok" });

  await page.goto("/");

  await expect(
    page.getByText("No link? No problem"),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: /Try it/ }),
  ).toBeVisible();
  // Said before pressing, because it is true of pressing.
  await expect(
    page.getByText("scrambled form of your IP address"),
  ).toBeVisible();
});

test("pressing it solves the challenge and opens a guest session", async ({
  page,
}) => {
  const calls = authCalls();
  const trialRequests: Array<Record<string, unknown>> = [];

  await mockBackend(page, {
    refresh: "gone",
    trial: "ok",
    calls,
    trialRequests,
  });

  await page.goto("/");
  await page.getByRole("button", { name: /Try it/ }).click();

  await waitForReady(page);
  await expect(page.getByText("Hi Guest! 👋")).toBeVisible();

  // One trial, paid with the right number: the mock's challenge hides 7.
  expect(calls.trial).toBe(1);
  const solution = JSON.parse(
    Buffer.from(
      String(trialRequests[0]?.solution),
      "base64",
    ).toString(),
  );
  expect(solution.number).toBe(7);
});

test("pressing twice opens one trial, not two", async ({
  page,
}) => {
  const calls = authCalls();

  await mockBackend(page, { refresh: "gone", trial: "ok", calls });

  await page.goto("/");
  const tryIt = page.getByRole("button", { name: /Try it/ });
  await tryIt.dblclick();

  await waitForReady(page);
  expect(calls.trial).toBe(1);
});

test("a second trial from the same address the same day is explained", async ({
  page,
}) => {
  await mockBackend(page, { refresh: "gone", trial: "used" });

  await page.goto("/");
  await page.getByRole("button", { name: /Try it/ }).click();

  await expect(
    page.getByText("You've already had today's trial"),
  ).toBeVisible();
  // A dead end now, so no button to press again.
  await expect(
    page.getByRole("button", { name: /Try it/ }),
  ).toHaveCount(0);
});

test("when today's trials are all gone, it says so", async ({
  page,
}) => {
  await mockBackend(page, { refresh: "gone", trial: "gone" });

  await page.goto("/");
  await page.getByRole("button", { name: /Try it/ }).click();

  await expect(
    page.getByText("Today's trials have all been taken"),
  ).toBeVisible();
});

test("with trials off, no link is the dead end it always was", async ({
  page,
}) => {
  await mockBackend(page, { refresh: "gone", trial: "off" });

  await page.goto("/");

  await expect(
    page.getByText("You'll need the chat link you were sent"),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: /Try it/ }),
  ).toHaveCount(0);
});

test("running out in a trial is worded for a guest, not a link", async ({
  page,
}) => {
  await mockBackend(page, { refresh: "gone", trial: "ok" });
  await page.route("**/chat/stream", (route) =>
    route.fulfill({
      status: 429,
      contentType: "application/json",
      body: JSON.stringify({ detail: "Query limit reached" }),
    }),
  );

  await page.goto("/");
  await page.getByRole("button", { name: /Try it/ }).click();
  await waitForReady(page);

  await page.getByLabel("Your question").fill("One more?");
  await page.getByLabel("Your question").press("Enter");

  await expect(
    page.getByText("That's all the questions in this trial"),
  ).toBeVisible();
});
