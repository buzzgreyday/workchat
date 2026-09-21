import { expect, test } from "@playwright/test";

import { mockBackend, openChat } from "./backend";

/**
 * The phone-shaped faults.
 *
 * Three things shipped that a desktop window cannot show, and the desktop
 * suite passed throughout: the document was 2rem taller than the screen, the
 * canvas behind it was white, and the composer's placeholder wrapped inside a
 * one-row textarea so the field scrolled before anything was typed. What they
 * have in common is that they are all invisible at 1280px and obvious at
 * 393px.
 *
 * The on-screen keyboard itself is not in here. Headless Chromium does not
 * have one, and a test that resized the viewport and called that a keyboard
 * would assert nothing that was ever broken. What is testable is the invariant
 * underneath it — a page exactly one screen tall, on a background that is
 * never white — and that is what these check.
 */
test.skip(
  ({ isMobile }) => !isMobile,
  "phone-sized layout only",
);

/** How much taller than the screen the document is. */
async function verticalOverflow(
  page: import("@playwright/test").Page,
): Promise<number> {
  return page.evaluate(() => {
    const el = document.scrollingElement;

    return el ? el.scrollHeight - el.clientHeight : 0;
  });
}

/** How much taller the field's content is than the field. */
async function composerOverflow(
  page: import("@playwright/test").Page,
): Promise<number> {
  return page
    .getByLabel("Your question")
    .evaluate(
      (el) => el.scrollHeight - el.clientHeight,
    );
}

test("the page is exactly one screen tall", async ({
  page,
}) => {
  await mockBackend(page);
  await openChat(page);

  await expect(
    page.getByLabel("Your question"),
  ).toBeVisible();

  // One pixel of slack for sub-pixel rounding, and no more. The old layout
  // was over by a full 2rem: `min-h-dvh` set a floor of one viewport and the
  // page padding was then added on top of it.
  expect(
    await verticalOverflow(page),
  ).toBeLessThanOrEqual(1);
});

test("nothing white is painted behind the chat", async ({
  page,
}) => {
  await mockBackend(page);
  await openChat(page);

  await expect(
    page.getByLabel("Your question"),
  ).toBeVisible();

  // The chat itself was always dark. What showed under it was the root
  // element, which inherited the white shadcn `--background` — so this asserts
  // the canvas, not the card.
  const canvas = await page.evaluate(
    () =>
      getComputedStyle(
        document.documentElement,
      ).backgroundColor,
  );

  expect(canvas).not.toBe("rgb(255, 255, 255)");
  expect(canvas).not.toBe("rgba(0, 0, 0, 0)");

  // The other half, and the half a background cannot do: the surfaces the page
  // does not own at all — scrollbars, the composer's caret and selection, the
  // fill behind a rubber-band — are painted from `color-scheme`.
  const scheme = await page.evaluate(
    () =>
      getComputedStyle(
        document.documentElement,
      ).colorScheme,
  );

  expect(scheme).toBe("dark");
});

test("the document cannot be scrolled off the chat at all", async ({
  page,
}) => {
  await mockBackend(page);
  await openChat(page);

  await expect(
    page.getByLabel("Your question"),
  ).toBeVisible();

  // A scroll with nowhere to go is honoured silently, so the assertion has to
  // be on where the page ended up rather than on the call having been made.
  await page.evaluate(() =>
    window.scrollTo(0, 5000),
  );

  await expect
    .poll(() => page.evaluate(() => window.scrollY))
    .toBe(0);
});

test("the browser is told to resize the layout for the keyboard", async ({
  page,
}) => {
  await mockBackend(page);
  await openChat(page);

  await expect(
    page.getByLabel("Your question"),
  ).toBeVisible();

  // Headless Chromium has no on-screen keyboard, so what is checked is the
  // instruction rather than the effect. `interactive-widget=resizes-content`
  // is what makes `dvh` shrink when a keyboard opens instead of leaving the
  // composer behind it; `viewport-fit=cover` is what makes the safe-area
  // insets `.chat-shell` pads with resolve to anything at all.
  const content = await page
    .locator('meta[name="viewport"]')
    .getAttribute("content");

  expect(content).toContain(
    "interactive-widget=resizes-content",
  );
  expect(content).toContain("viewport-fit=cover");
});

test("the composer starts as one line, and does not scroll", async ({
  page,
}) => {
  await mockBackend(page);
  await openChat(page);

  const composer = page.getByLabel(
    "Your question",
  );

  await expect(composer).toBeEnabled();
  await expect(composer).toHaveAttribute(
    "placeholder",
    "Ask a question…",
  );

  expect(
    await composerOverflow(page),
  ).toBeLessThanOrEqual(1);

  // Under 16px, iOS Safari zooms the whole page the moment the field takes
  // focus — and does not zoom back out, which leaves the layout offset behind
  // the keyboard and looks exactly like the chat having broken.
  const fontSize = await composer.evaluate((el) =>
    Number.parseFloat(
      getComputedStyle(el).fontSize,
    ),
  );

  expect(fontSize).toBeGreaterThanOrEqual(16);
});

test("a shut composer's reason fits on one line too", async ({
  page,
}) => {
  // Nothing left to ask with, which is one of the two ways the composer shuts
  // — and the one whose placeholder was longest.
  await mockBackend(page, { remaining: 0 });
  await openChat(page);

  const composer = page.getByLabel(
    "Your question",
  );

  await expect(composer).toBeDisabled();
  await expect(composer).toHaveAttribute(
    "placeholder",
    "No questions left",
  );

  expect(
    await composerOverflow(page),
  ).toBeLessThanOrEqual(1);
  expect(
    await verticalOverflow(page),
  ).toBeLessThanOrEqual(1);
});

test("the composer shrinks back after a multi-line question is sent", async ({
  page,
}) => {
  await mockBackend(page);
  await openChat(page);

  const composer = page.getByLabel(
    "Your question",
  );

  await expect(composer).toBeEnabled();

  const oneLine = await composer.evaluate(
    (el) => el.clientHeight,
  );

  await composer.fill(
    "First line\nSecond line\nThird line",
  );

  const grown = await composer.evaluate(
    (el) => el.clientHeight,
  );

  // It must genuinely have grown, or the shrink below proves nothing.
  expect(grown).toBeGreaterThan(oneLine);

  await composer.press("Enter");

  await expect(composer).toHaveValue("");

  // The regression: the height was set imperatively in `onChange`, and sending
  // clears the value through state rather than through a change event, so the
  // box stayed at the height of a question that was no longer there.
  await expect
    .poll(() =>
      composer.evaluate(
        (el) => el.clientHeight,
      ),
    )
    .toBe(oneLine);
});
