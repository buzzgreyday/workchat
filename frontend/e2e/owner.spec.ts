import { expect, test } from "@playwright/test";

import { mockBackend, openChat } from "./backend";

/**
 * Whose CV this is, read from the running server's environment.
 *
 * The values under test are set on the webServer in playwright.config.ts, not
 * in any file, which is the claim worth proving: a `NEXT_PUBLIC_` variable
 * would have been frozen into the bundle by `next build` and could not differ
 * from whatever the image was built with.
 */

test("the tab names the configured owner, under the site's own title", async ({
  page,
}) => {
  await mockBackend(page);
  await openChat(page);

  // The top bar says "Workchat" and no more — the name lives in the tab and
  // the metadata, which are what is read from the environment here.
  await expect(
    page.getByRole("heading", { name: "Workchat", exact: true }),
  ).toBeVisible();

  await expect(page).toHaveTitle(
    "Workchat with Ada Lovelace",
  );
});

test("a configured link is followed, and an empty one is not rendered", async ({
  page,
}) => {
  await mockBackend(page);
  await openChat(page);

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

test("the owner's own site is linked first, by its name, in this tab", async ({
  page,
}) => {
  await mockBackend(page);
  await openChat(page);

  // OWNER_WEBSITE_URL in playwright.config.ts.
  const site = page.getByRole("link", { name: "ada.example.com" });

  await expect(site).toHaveAttribute("href", "https://ada.example.com");
  // Where someone who came for the chat goes next: not a new tab.
  await expect(site).not.toHaveAttribute("target", /.*/);
});

test("the site's top bar is the only header", async ({
  page,
}) => {
  await mockBackend(page);
  await openChat(page);

  // The site frames the chat as any host would, with the chat's own header
  // turned off. Two headings would mean both came back.
  await expect(page.getByRole("heading")).toHaveCount(1);
  await expect(
    page.locator("header").getByText(/questions left/),
  ).toBeVisible();
});
