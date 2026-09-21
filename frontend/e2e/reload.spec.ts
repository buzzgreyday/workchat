import { expect, test } from "@playwright/test";

import {
  mockBackend,
  openChat,
  replyWith,
} from "./backend";

/**
 * What survives F5.
 *
 * `useSession` already resumes from the refresh cookie so a reload does not
 * cost the hirer their single-use link. The conversation used to be dropped
 * anyway: the agent lost every turn of context, and the backend — handed a
 * null conversation id — opened a second row for the same person.
 *
 * Worth knowing about the reload itself: the credential is stripped from the
 * URL once it is spent, so F5 has *always* landed on the cookie-resume branch
 * — even back when these tests opened a v1 link. What the move to `?claim=`
 * fixes is the first load, which used to exercise a path being retired. The
 * assertions below were never affected either way.
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

  await openChat(page);

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

  // A claim of its own per hirer: the mock keys the token it hands back on
  // the grant configured above, and the point of the test is that the two
  // transcripts never meet.
  await openChat(page, { claim: "claim-ada" });

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

  await openChat(page, {
    claim: "claim-grace",
  });

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
