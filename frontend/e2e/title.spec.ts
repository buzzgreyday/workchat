import { expect, test } from "@playwright/test";

import { mockBackend, openChat } from "./backend";

/**
 * The title: WORK and CHAT trade places now and then.
 *
 * What is worth pinning is not the choreography but its edges: the halves
 * swap, a screen reader hears the word and never the swap, and reduced motion
 * means none of it happens.
 */

const shown = (page: import("@playwright/test").Page) =>
  page.locator("h1 [aria-hidden='true']").textContent();

test("the two halves trade places", async ({ page }) => {
  await mockBackend(page);
  await openChat(page);

  await expect.poll(() => shown(page), { timeout: 8000 }).toBe("chatWork");

  // Swapped, the heading still says what it is.
  await expect(
    page.getByRole("heading", { name: "Workchat", exact: true }),
  ).toBeVisible();
});

test("the title stays still when reduced motion is asked for", async ({
  page,
}) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await mockBackend(page);
  await openChat(page);

  // Past the point where the first switch would have happened.
  await page.waitForTimeout(4500);

  expect(await shown(page)).toBe("Workchat");
});
