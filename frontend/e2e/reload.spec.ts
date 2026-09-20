import { expect, test } from "@playwright/test";

import {
  fakeToken,
  mockBackend,
  replyWith,
} from "./backend";

/**
 * What survives F5.
 *
 * `useSession` already resumes from the refresh cookie so a reload does not
 * cost the hirer their single-use link. The conversation used to be dropped
 * anyway: the agent lost every turn of context, and the backend — handed a
 * null conversation id — opened a second row for the same person.
 */

test("the transcript and the conversation survive a reload", async ({
  page,
}) => {
  const requests: Array<Record<string, unknown>> =
    [];

  await mockBackend(page, {
    requests,
    stream: replyWith("He works at iEDI.", {
      conversationId: "conversation-7",
    }),
  });

  await page.goto(`/?token=${fakeToken()}`);

  const composer = page.getByLabel(
    "Your question",
  );

  await composer.fill("Where does he work?");
  await composer.press("Enter");

  await expect(
    page.getByText("He works at iEDI."),
  ).toBeVisible();

  await page.reload();

  // Both halves of the turn are still on screen.
  await expect(
    page.getByText("Where does he work?"),
  ).toBeVisible();
  await expect(
    page.getByText("He works at iEDI."),
  ).toBeVisible();

  await composer.fill("And before that?");
  await composer.press("Enter");

  await expect
    .poll(() => requests.length)
    .toBe(2);

  // The same conversation, not a second one — and the agent still has the
  // first turn to reason from.
  expect(requests[1]?.conversation_id).toBe(
    "conversation-7",
  );
  expect(
    (requests[1]?.history as unknown[])?.length,
  ).toBeGreaterThan(0);
});

test("a different link in the same tab does not inherit the last one's transcript", async ({
  page,
}) => {
  await mockBackend(page, {
    grantId: "grant-1",
    sub: "Ada Lovelace",
    stream: replyWith(
      "Something only Ada asked about.",
    ),
  });

  await page.goto(
    `/?token=${fakeToken({ grantId: "grant-1", sub: "Ada Lovelace" })}`,
  );

  const composer = page.getByLabel(
    "Your question",
  );

  await composer.fill("Ada's question");
  await composer.press("Enter");

  await expect(
    page.getByText(
      "Something only Ada asked about.",
    ),
  ).toBeVisible();

  // A second hirer opens their own link in the same tab. The stored transcript
  // is keyed by grant precisely so this cannot show them someone else's.
  await page.unrouteAll({
    behavior: "ignoreErrors",
  });
  await mockBackend(page, {
    grantId: "grant-2",
    sub: "Grace Hopper",
  });

  await page.goto(
    `/?token=${fakeToken({ grantId: "grant-2", sub: "Grace Hopper" })}`,
  );

  await expect(
    page.getByText("Hi Grace Hopper! 👋"),
  ).toBeVisible();
  await expect(
    page.getByText("Ada's question"),
  ).toHaveCount(0);
  await expect(
    page.getByText(
      "Something only Ada asked about.",
    ),
  ).toHaveCount(0);
});
