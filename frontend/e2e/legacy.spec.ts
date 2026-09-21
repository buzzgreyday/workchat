import { expect, test } from "@playwright/test";

import {
  authCalls,
  mockBackend,
  openLegacyChat,
  replyWith,
} from "./backend";

/**
 * The v1 `?token=` links, and only those.
 *
 * A v1 link carries the access token itself, in the URL — which is why it is
 * being retired: a URL is copied into browser histories, sent as a referrer,
 * and written to every proxy log on the way. The rest of the suite drives
 * `?claim=`, the shape that replaces it.
 *
 * This file is the leash. Those links are in inboxes and cannot be reissued,
 * so the behaviour has to keep working until the last one expires — and then
 * this file should be deleted along with the code paths it guards. Every title
 * is prefixed `legacy:` so `--grep legacy` finds the lot in one pass.
 */

test("legacy: the link is the token, so the greeting lands on the first paint", async ({
  page,
}) => {
  const calls = authCalls();

  await mockBackend(page, {
    sub: "Alan Turing",
    calls,
  });

  await openLegacyChat(page, {
    sub: "Alan Turing",
  });

  await expect(
    page.getByText("Hi Alan Turing! 👋"),
  ).toBeVisible();

  // No typing dots: there was no round trip to wait through.
  await expect(
    page.getByLabel("Generating a reply"),
  ).toHaveCount(0);

  // And the reason why, which the screen cannot show — nothing was exchanged.
  // Without this the test would still pass if `isV1` stopped being honoured
  // and the page merely happened to be quick.
  expect(calls.claim).toBe(0);
});

test("legacy: the token does not survive in the address bar", async ({
  page,
}) => {
  await mockBackend(page);

  await openLegacyChat(page);

  await expect(page).toHaveURL(
    (url) => !url.search.includes("token"),
  );
});

test("legacy: the grant is read from `jti`, so the conversation is filed under it", async ({
  page,
}) => {
  await mockBackend(page, {
    grantId: "legacy-grant-1",
    stream: replyWith("He works at iEDI."),
  });

  await openLegacyChat(page, {
    grantId: "legacy-grant-1",
  });

  const composer = page.getByLabel(
    "Your question",
  );

  await composer.fill("Where does he work?");
  await composer.press("Enter");

  await expect(
    page.getByText("He works at iEDI."),
  ).toBeVisible();

  // The only coverage anywhere of `claims.tid ?? claims.jti` in lib/auth.ts.
  // A v1 token has no `tid`, so the grant can only come from `jti`; every
  // other spec hands the page a v2-shaped token that has one.
  //
  // This works as an assertion because `saveConversation` returns early on an
  // empty grant — so a regression to "" writes nothing and `stored` is null,
  // rather than quietly filing the transcript under the wrong key.
  const stored = await page.evaluate(() =>
    window.sessionStorage.getItem(
      "workchat:conversation",
    ),
  );

  expect(stored).not.toBeNull();
  expect(
    JSON.parse(stored ?? "{}").grantId,
  ).toBe("legacy-grant-1");
});

test("legacy: a 401 is terminal, because there is nothing to refresh with", async ({
  page,
}) => {
  const calls = authCalls();

  await mockBackend(page, { calls });

  // The session dies mid-visit. On a v2 link this would be absorbed by one
  // refresh and a retry; a v1 link has no refresh cookie behind it, so the
  // only honest thing is to stop.
  await page.route("**/chat/stream", (route) =>
    route.fulfill({
      status: 401,
      contentType: "application/json",
      body: JSON.stringify({
        detail: "Token expired",
      }),
    }),
  );

  await openLegacyChat(page);

  const composer = page.getByLabel(
    "Your question",
  );

  await composer.fill("Anything at all?");
  await composer.press("Enter");

  await expect(
    page.getByText("This link has expired"),
  ).toBeVisible();

  // The part that matters and is invisible: no refresh was attempted.
  expect(calls.refresh).toBe(0);
});
