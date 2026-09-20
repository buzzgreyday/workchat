import { expect, test } from "@playwright/test";

import { fakeToken, mockBackend } from "./backend";

/**
 * Whose CV this is, read from the running server's environment.
 *
 * The values under test are set on the webServer in playwright.config.ts, not
 * in any file, which is the claim worth proving: a `NEXT_PUBLIC_` variable
 * would have been frozen into the bundle by `next build` and could not differ
 * from whatever the image was built with.
 */

test("the header and the tab name the configured owner", async ({
  page,
}) => {
  await mockBackend(page);
  await page.goto(`/?token=${fakeToken()}`);

  await expect(
    page.getByRole("heading", {
      name: "Workchat with Ada Lovelace",
    }),
  ).toBeVisible();

  await expect(page).toHaveTitle(
    "Workchat with Ada Lovelace",
  );
});

test("a configured link is followed, and an empty one is not rendered", async ({
  page,
}) => {
  await mockBackend(page);
  await page.goto(`/?token=${fakeToken()}`);

  await expect(
    page.getByRole("link", { name: "GitHub" }),
  ).toHaveAttribute(
    "href",
    "https://github.com/ada",
  );

  // OWNER_LINKEDIN_URL is set but empty. Unset would mean "use the default";
  // empty means "there isn't one", and the difference matters because the
  // default is a real person's profile.
  await expect(
    page.getByRole("link", {
      name: "LinkedIn",
    }),
  ).toHaveCount(0);
});
