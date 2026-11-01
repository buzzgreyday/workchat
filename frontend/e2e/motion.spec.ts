import { expect, test } from "@playwright/test";

import { mockBackend, openChat } from "./backend";

/**
 * The endless animations, with and without reduced motion asked for. Their classes
 * are put on the page by hand: they only show while a reply is being written, and
 * what is checked here is the stylesheet, not the streaming.
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
      dot: getComputedStyle(add("chat-typing-dot")).animationName,
      progress: getComputedStyle(add("chat-progress")).animationName,
    };
  });
}

test("the typing dots and the progress line move by default", async ({
  page,
}) => {
  await mockBackend(page);
  await openChat(page);

  expect(await animations(page)).toEqual({
    dot: "chat-typing-bounce",
    progress: "chat-progress-pulse",
  });
});

test("they hold still with reduced motion asked for", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await mockBackend(page);
  await openChat(page);

  expect(await animations(page)).toEqual({ dot: "none", progress: "none" });
});
