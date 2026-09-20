import { expect, test } from "@playwright/test";

import { fakeToken, mockBackend } from "./backend";

/**
 * What the page says before it knows who is reading.
 *
 * A v1 link *is* the access token, so the hirer can be greeted on the first
 * paint. A claim link costs a round trip first, and the greeting used to fill
 * that gap with a bare "Hi! 👋" addressed to nobody, then flip to their name.
 */

test("a claim link shows it is working, then greets by name", async ({
  page,
}) => {
  // Hold the exchange open so the loading state is observable rather than a
  // race — this is precisely the window the greeting used to get wrong.
  let release: () => void = () => {};
  const held = new Promise<void>((resolve) => {
    release = resolve;
  });

  await mockBackend(page, {
    sub: "Grace Hopper",
  });

  await page.route(
    "**/v2/auth/claim",
    async (route) => {
      await held;

      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({
          access_token: fakeToken({
            sub: "Grace Hopper",
          }),
          token_type: "bearer",
          expires_in: 900,
          refresh_expires_in: 604800,
        }),
      });
    },
  );

  await page.goto("/?claim=a-claim-token");

  await expect(
    page.getByLabel("Generating a reply"),
  ).toBeVisible();
  await expect(
    page.getByText("Hi!", { exact: true }),
  ).toHaveCount(0);

  release();

  await expect(
    page.getByText("Hi Grace Hopper! 👋"),
  ).toBeVisible();

  // The dots must not linger behind the text — the greeting carries a status
  // as well as content, and forgetting that left it streaming forever.
  await expect(
    page.getByLabel("Generating a reply"),
  ).toHaveCount(0);
});

test("a v1 link greets immediately, with no thinking state", async ({
  page,
}) => {
  await mockBackend(page, { sub: "Alan Turing" });

  await page.goto(
    `/?token=${fakeToken({ sub: "Alan Turing" })}`,
  );

  await expect(
    page.getByText("Hi Alan Turing! 👋"),
  ).toBeVisible();
  await expect(
    page.getByLabel("Generating a reply"),
  ).toHaveCount(0);
});

test("the credential does not survive in the address bar", async ({
  page,
}) => {
  await mockBackend(page);

  await page.goto(`/?token=${fakeToken()}`);

  await expect(page).toHaveURL(
    (url) => !url.search.includes("token"),
  );
});
