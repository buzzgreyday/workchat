import { expect, test } from "@playwright/test";

import { mockBackend, openChat } from "./backend";

/**
 * The two endless animations, with and without reduced motion asked for. Their
 * classes are put on the page by hand: both only show while a reply is being
 * written, and what is checked here is the stylesheet, not the streaming.
 */
async function animations(page: import("@playwright/test").Page) {
  return page.evaluate(() => {
    const add = (name: string) => {
      const element = document.createElement("div");
      element.className = name;
      document.body.append(element);
      return element;
    };
    return {
      ring: getComputedStyle(add("chat-avatar-glow"), "::before").animationName,
      dot: getComputedStyle(add("chat-typing-dot")).animationName,
    };
  });
}

test("the avatar's ring and the typing dots move by default", async ({
  page,
}) => {
  await mockBackend(page);
  await openChat(page);

  expect(await animations(page)).toEqual({
    ring: "chat-ring-spin",
    dot: "chat-typing-bounce",
  });
});

test("they hold still with reduced motion asked for", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await mockBackend(page);
  await openChat(page);

  expect(await animations(page)).toEqual({ ring: "none", dot: "none" });
});
