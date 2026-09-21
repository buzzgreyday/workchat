import {
  expect,
  test,
  type Page,
} from "@playwright/test";

import { mockBackend, openChat } from "./backend";

/**
 * The layout takes its height from the visual viewport.
 *
 * `interactive-widget=resizes-content` covers Chromium; iOS Safari ignores it
 * and shrinks only the visual viewport, so the height is measured instead of
 * assumed.
 *
 * Be clear about what this file proves. Headless Chromium has no on-screen
 * keyboard, and `setViewportSize` resizes the *layout* viewport — the Android
 * shape, which already worked. So these tests prove the plumbing: that the
 * property is written, that it tracks a change, that it is guarded against
 * pinch-zoom, and that a browser without the API still fills the screen. They
 * do not prove the iOS outcome. That is a real device, by hand.
 */

const appHeight = (page: Page) =>
  page.evaluate(() =>
    document.documentElement.style.getPropertyValue(
      "--app-height",
    ),
  );

test("the height comes from the visual viewport", async ({
  page,
}) => {
  await mockBackend(page);
  await openChat(page);

  await expect(
    page.getByLabel("Your question"),
  ).toBeVisible();

  await expect
    .poll(() => appHeight(page))
    .not.toBe("");

  const measured = await page.evaluate(() => ({
    property: parseFloat(
      document.documentElement.style.getPropertyValue(
        "--app-height",
      ),
    ),
    visual: window.visualViewport?.height ?? 0,
    layout: document.documentElement.clientHeight,
  }));

  expect(measured.property).toBe(
    Math.round(measured.visual),
  );

  // With no keyboard up the two viewports agree, so the hook must not have
  // shrunk anything. This is the assertion that would catch it measuring the
  // wrong thing and quietly cropping the page.
  expect(
    Math.abs(
      measured.property - measured.layout,
    ),
  ).toBeLessThanOrEqual(1);
});

test("the height follows the viewport down", async ({
  page,
}) => {
  await mockBackend(page);
  await openChat(page);

  await expect(
    page.getByLabel("Your question"),
  ).toBeVisible();

  // Not a keyboard — but it is a visual-viewport resize, which is the event
  // the hook actually listens for. A property that is written once and never
  // updated passes the test above and fails this one.
  await page.setViewportSize({
    width: 393,
    height: 520,
  });

  await expect
    .poll(() => appHeight(page))
    .toBe("520px");

  const main = await page
    .locator("main")
    .boundingBox();

  expect(
    Math.abs((main?.height ?? 0) - 520),
  ).toBeLessThanOrEqual(1);
});

test("pinch-zoom does not shrink the app", async ({
  page,
}) => {
  // The one thing Playwright cannot produce, so the one thing worth stubbing:
  // zoomed in, `visualViewport.height` reports the slice of the page on
  // screen, and honouring it would crop the chat to that slice.
  await page.addInitScript(() => {
    const viewport = window.visualViewport;

    if (viewport) {
      Object.defineProperty(viewport, "scale", {
        get: () => 2,
        configurable: true,
      });
    }
  });

  await mockBackend(page);
  await openChat(page);

  await expect(
    page.getByLabel("Your question"),
  ).toBeVisible();

  // Nothing written: the stylesheet's `100dvh` fallback is the right answer
  // while the measurement is meaningless.
  expect(await appHeight(page)).toBe("");

  const filled = await page.evaluate(() => {
    const main =
      document.querySelector("main");

    return (
      (main?.getBoundingClientRect().height ??
        0) -
      document.documentElement.clientHeight
    );
  });

  expect(Math.abs(filled)).toBeLessThanOrEqual(1);
});

test("a browser without the API still fills the screen", async ({
  page,
}) => {
  await page.addInitScript(() => {
    Object.defineProperty(
      window,
      "visualViewport",
      {
        get: () => null,
        configurable: true,
      },
    );
  });

  await mockBackend(page);
  await openChat(page);

  await expect(
    page.getByLabel("Your question"),
  ).toBeVisible();

  expect(await appHeight(page)).toBe("");

  const overflow = await page.evaluate(() => {
    const element = document.scrollingElement;

    return element
      ? element.scrollHeight -
          element.clientHeight
      : 0;
  });

  expect(overflow).toBeLessThanOrEqual(1);
});
