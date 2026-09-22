import { expect, test } from "@playwright/test";

import {
  gate,
  mockBackend,
  openChat,
  replyWith,
} from "./backend";

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

/**
 * The 0.7.1 fault, which the test above could not see.
 *
 * Auto-scroll followed the transcript by calling `scrollIntoView()` on a
 * sentinel at the end of it, once per token. `scrollIntoView` is not scoped to
 * the nearest scroller: it scrolls *every* ancestor that can move, the
 * document included. On a phone, in the window where the keyboard is animating
 * and `--app-height` is a frame behind it, that walked the whole page up the
 * screen and left it there, where `overflow: hidden` on `html` meant nothing
 * could scroll it back.
 *
 * The damage itself cannot be reproduced here, and a test that tries is a test
 * that always passes. `overflow: hidden` on the root element propagates to the
 * viewport, which leaves the document with no scrolling area at all — making
 * the page taller than the screen does not create one, and `window.scrollY`
 * stays 0 in this app whatever a script does to it. A phone's visual viewport
 * is not so constrained, which is why the fault was only ever seen on one.
 *
 * So the call is watched for rather than its effect. Auto-scroll has no
 * business moving anything outside the transcript, and `scrollIntoView` is the
 * one API here that cannot promise that; writing `scrollTop` can only ever
 * move the element it is written to.
 *
 * The reply is deliberately short. The mock delivers a whole answer in a
 * single chunk, and the old guard — "is the transcript near its bottom, now
 * that the new content has landed?" — bails out on a long one without
 * scrolling at all, so a long reply would watch for a call that never comes
 * for the wrong reason. Short, it stays near the bottom, the guard passes, and
 * the old code reaches `scrollIntoView` exactly as it did on a phone.
 */
test("a streamed reply is followed without reaching outside the transcript", async ({
  page,
}) => {
  await page.addInitScript(() => {
    const counter = { calls: 0 };

    (
      window as unknown as {
        __scrollIntoView: { calls: number };
      }
    ).__scrollIntoView = counter;

    const original =
      Element.prototype.scrollIntoView;

    Element.prototype.scrollIntoView =
      function (this: Element, ...args: []) {
        counter.calls += 1;

        return original.apply(this, args);
      };
  });

  const reply = gate();

  await mockBackend(page, {
    holdStream: reply.held,
    stream: replyWith("Backend work, in Python."),
  });

  await openChat(page);

  const composer = page.getByLabel(
    "Your question",
  );

  await expect(composer).toBeVisible();

  await composer.fill("What does he do?");
  await composer.press("Enter");

  // Zeroed once the question is out: reaching and focusing the composer is
  // Playwright's own scrolling, and only what the reply does is in question.
  await page.evaluate(() => {
    (
      window as unknown as {
        __scrollIntoView: { calls: number };
      }
    ).__scrollIntoView.calls = 0;
  });

  reply.release();

  await expect(
    page.getByText("Backend work, in Python."),
  ).toBeVisible();

  // Given a frame to do it in — the old scroll was smooth, and a smooth scroll
  // has not moved anything yet on the frame the text appears. The call itself
  // is synchronous, so one frame is enough for it to have been counted.
  await page.evaluate(
    () =>
      new Promise((resolve) =>
        requestAnimationFrame(resolve),
      ),
  );

  expect(
    await page.evaluate(
      () =>
        (
          window as unknown as {
            __scrollIntoView: { calls: number };
          }
        ).__scrollIntoView.calls,
    ),
  ).toBe(0);
});
