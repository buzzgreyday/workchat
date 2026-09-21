import { expect, test } from "@playwright/test";

import { mockBackend, openChat } from "./backend";

/**
 * The two representations of the background colour agree.
 *
 * `themeColor` in the layout's viewport export paints the browser's own chrome
 * — the status bar above the page on a phone. It has to be a literal, because
 * a `<meta>` tag is serialised during the server render, where no CSS has been
 * parsed and a custom property does not exist yet.
 *
 * So there are two copies of one colour, and a comment asking the next person
 * to remember is not a mechanism. This is.
 */
test("the browser chrome is painted the same colour as the page", async ({
  page,
}) => {
  await mockBackend(page);
  await openChat(page);

  const declared = await page
    .locator('meta[name="theme-color"]')
    .getAttribute("content");

  expect(declared).toBeTruthy();

  // Both sides painted into a canvas before comparing. `getComputedStyle`
  // hands back an `oklch()` for an oklch author value and a hex for a hex, so
  // comparing the strings would be comparing notations rather than colours.
  const [chrome, page_] = await page.evaluate(
    (hex) => {
      const toRgb = (value: string) => {
        const surface =
          document.createElement("canvas");
        surface.width = 1;
        surface.height = 1;

        const context =
          surface.getContext("2d");

        if (!context) {
          return [-1, -1, -1];
        }

        context.fillStyle = value;
        context.fillRect(0, 0, 1, 1);

        return Array.from(
          context.getImageData(0, 0, 1, 1)
            .data,
        ).slice(0, 3);
      };

      return [
        toRgb(hex),
        toRgb(
          getComputedStyle(
            document.documentElement,
          )
            .getPropertyValue("--chat-bg")
            .trim(),
        ),
      ];
    },
    declared as string,
  );

  // One channel of rounding is the conversion, not a drift.
  chrome.forEach((channel, index) =>
    expect(
      Math.abs(channel - (page_[index] ?? -1)),
    ).toBeLessThanOrEqual(1),
  );
});
