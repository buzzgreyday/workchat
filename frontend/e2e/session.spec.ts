import { expect, test } from "@playwright/test";

import {
  authCalls,
  mockBackend,
  openChat,
  replyWith,
  waitForReady,
} from "./backend";

/**
 * The ways a session fails to open, and the way it renews itself.
 *
 * `useSession` has five statuses and, until this file, one of them had a test.
 * The other four are the interesting ones: they are what a hirer meets when
 * their link has already been used, when the exchange breaks, when they arrive
 * with nothing at all, and when their access token quietly expires mid-visit.
 *
 * All of it is said by the agent rather than by a banner — the transcript is
 * where this app explains itself.
 */

test("a spent claim link says so, and the composer stays shut", async ({
  page,
}) => {
  await mockBackend(page, { claim: "spent" });

  await openChat(page);

  await expect(
    page.getByText(
      "This chat link has already been used",
    ),
  ).toBeVisible();

  const composer = page.getByLabel(
    "Your question",
  );

  await expect(composer).toBeDisabled();
  await expect(composer).toHaveAttribute(
    "placeholder",
    "Link can't start a session",
  );
});

test("a claim that will not exchange says the link may have expired", async ({
  page,
}) => {
  await mockBackend(page, { claim: "error" });

  await openChat(page);

  await expect(
    page.getByText(
      "I couldn't open a session from this link",
    ),
  ).toBeVisible();
});

test("arriving with no link at all asks for one", async ({
  page,
}) => {
  // No claim in the URL and no cookie to resume from: the shape of someone who
  // typed the address in, or whose tab outlived its session.
  await mockBackend(page, { refresh: "gone" });

  await page.goto("/");

  await expect(
    page.getByText(
      "You'll need the chat link you were sent",
    ),
  ).toBeVisible();
});

test("the claim does not survive in the address bar", async ({
  page,
}) => {
  await mockBackend(page);

  await openChat(page);
  await waitForReady(page);

  // A different effect from the v1 strip covered in legacy.spec.ts: this one
  // runs in the exchange's `finally`, *after* it settles, so that a reload
  // arriving before the claim lands can still retry rather than finding an
  // empty URL.
  await expect(page).toHaveURL(
    (url) => !url.search.includes("claim"),
  );
});

test("an expired access token is refreshed, and the question still goes through", async ({
  page,
}) => {
  const calls = authCalls();
  let attempts = 0;

  await mockBackend(page, {
    calls,
    stream: replyWith("He works at iEDI."),
  });

  await openChat(page);
  await waitForReady(page);

  // The first question meets a dead access token. Re-routed after the page is
  // open so the claim exchange itself is untouched.
  await page.route("**/chat/stream", (route) => {
    attempts += 1;

    if (attempts === 1) {
      return route.fulfill({
        status: 401,
        contentType: "application/json",
        body: JSON.stringify({
          detail: "Token expired",
        }),
      });
    }

    return route.fulfill({
      contentType: "text/event-stream",
      body:
        "data: " +
        JSON.stringify({
          type: "token",
          value: "He works at iEDI.",
        }) +
        "\n\n" +
        "data: " +
        JSON.stringify({
          type: "done",
          history: [
            {
              role: "assistant",
              content: "He works at iEDI.",
            },
          ],
          usage: {
            used: 1,
            remaining: 4,
            max: 5,
          },
          conversation_id: "conversation-1",
        }) +
        "\n\n",
    });
  });

  const composer = page.getByLabel(
    "Your question",
  );

  await composer.fill("Where does he work?");
  await composer.press("Enter");

  // The hirer sees an answer, not a failure: the 401 was absorbed.
  await expect(
    page.getByText("He works at iEDI."),
  ).toBeVisible();

  // Exactly one refresh — the claim exchange is not a refresh, and a second
  // would mean the retry had itself been retried.
  expect(calls.refresh).toBe(1);
  expect(attempts).toBe(2);
});

test("a refresh that lost the race is retried once", async ({
  page,
}) => {
  const calls = authCalls();
  let attempts = 0;

  await mockBackend(page, {
    calls,
    // Another tab rotated first. Inside the grace window that is one client
    // racing itself, not a replay, and the successor is already in the cookie
    // jar — so a single retry picks it up.
    refresh: "conflictOnce",
  });

  await openChat(page);
  await waitForReady(page);

  await page.route("**/chat/stream", (route) => {
    attempts += 1;

    if (attempts === 1) {
      return route.fulfill({
        status: 401,
        contentType: "application/json",
        body: JSON.stringify({
          detail: "Token expired",
        }),
      });
    }

    return route.fulfill({
      contentType: "text/event-stream",
      body:
        "data: " +
        JSON.stringify({
          type: "token",
          value: "Still here.",
        }) +
        "\n\n" +
        "data: " +
        JSON.stringify({
          type: "done",
          history: [],
          usage: {
            used: 1,
            remaining: 4,
            max: 5,
          },
          conversation_id: "conversation-1",
        }) +
        "\n\n",
    });
  });

  const composer = page.getByLabel(
    "Your question",
  );

  await composer.fill("Anything?");
  await composer.press("Enter");

  await expect(
    page.getByText("Still here."),
  ).toBeVisible();

  // Two: the 409 and the retry that succeeded. Without the retry the hirer
  // would have been logged out of a session that was never actually gone.
  expect(calls.refresh).toBe(2);
});
