import { expect, test, type Page } from "@playwright/test";

import { doneFrame, mockBackend, openChat } from "./backend";

/**
 * Progress is about what shows *between* frames, which a route's fulfilled body
 * cannot express: it arrives all at once. So `fetch` hands this one endpoint a
 * stream the test writes to, a frame at a time.
 */
async function controlStream(page: Page) {
  await page.addInitScript(() => {
    const realFetch = window.fetch.bind(window);
    const encoder = new TextEncoder();
    const scope = window as unknown as {
      pushFrame: (frame: unknown) => void;
      endStream: () => void;
      requests: number;
    };

    scope.requests = 0;

    window.fetch = (input, init) => {
      if (!String(input).endsWith("/chat/stream")) {
        return realFetch(input, init);
      }

      scope.requests += 1;

      return Promise.resolve(
        new Response(
          new ReadableStream({
            start(controller) {
              scope.pushFrame = (frame) =>
                controller.enqueue(
                  encoder.encode(`data: ${JSON.stringify(frame)}\n\n`),
                );
              scope.endStream = () => controller.close();
            },
          }),
          { headers: { "Content-Type": "text/event-stream" } },
        ),
      );
    };
  });

  const started = () =>
    expect
      .poll(() =>
        page.evaluate(
          () =>
            typeof (window as unknown as { pushFrame?: unknown }).pushFrame,
        ),
      )
      .toBe("function");

  return {
    started,
    push: (frame: unknown) =>
      page.evaluate((value) => {
        (window as unknown as { pushFrame: (f: unknown) => void }).pushFrame(
          value,
        );
      }, frame),
    end: () =>
      page.evaluate(() => {
        (window as unknown as { endStream: () => void }).endStream();
      }),
  };
}

async function ask(page: Page, question: string) {
  const composer = page.getByLabel("Your question");

  await composer.fill(question);
  await composer.press("Enter");
}

const state = (code: string) => ({ type: "state", code });
const thought = (code: string) => ({ type: "thought", code });

test("the wait says what is happening, step by step, until the reply starts", async ({
  page,
}) => {
  const stream = await controlStream(page);

  await mockBackend(page);
  await openChat(page);
  await ask(page, "What does he do?");
  await stream.started();

  await expect(page.getByText("Sending…")).toBeVisible();

  await stream.push(state("preprocessing"));
  await expect(page.getByText("Reading your question…")).toBeVisible();

  await stream.push(state("composing"));
  await expect(page.getByText("Thinking…")).toBeVisible();

  await stream.push(thought("knowledge_lookup"));
  await expect(page.getByText("Searching the CV…")).toBeVisible();

  // The dots are for a session opening, not for this.
  await expect(page.locator(".typing-dots")).toHaveCount(0);
});

test("the first word replaces the line at once, held or not", async ({
  page,
}) => {
  const stream = await controlStream(page);

  await mockBackend(page);
  await openChat(page);
  await ask(page, "What does he do?");
  await stream.started();

  await stream.push(thought("knowledge_lookup"));
  await stream.push({ type: "token", value: "Backend" });

  await expect(page.getByText("Backend")).toBeVisible();
  await expect(page.locator(".chat-progress")).toHaveCount(0);

  await stream.push(doneFrame({ reply: "Backend" }));
  await stream.end();
  await expect(page.getByLabel("Your question")).toBeEnabled();
});

test("a step arriving during a hold waits, and the latest one wins", async ({
  page,
}) => {
  const stream = await controlStream(page);

  await mockBackend(page);
  await openChat(page);
  await ask(page, "What does he do?");
  await stream.started();

  await stream.push(state("preprocessing"));
  await stream.push(state("composing"));
  await stream.push(thought("knowledge_lookup"));

  await expect(page.getByText("Searching the CV…")).toBeVisible();
  await expect(page.getByText("Reading your question…")).toHaveCount(0);
});

test("a code this page has no words for changes nothing", async ({ page }) => {
  const stream = await controlStream(page);

  await mockBackend(page);
  await openChat(page);
  await ask(page, "What does he do?");
  await stream.started();

  await stream.push(thought("knowledge_lookup"));
  await expect(page.getByText("Searching the CV…")).toBeVisible();

  await stream.push(thought("something_new"));
  await page.waitForTimeout(600);

  await expect(page.getByText("Searching the CV…")).toBeVisible();
  await expect(page.getByText("something_new")).toHaveCount(0);
});

test("a screen reader is told one thing, not every step", async ({ page }) => {
  const stream = await controlStream(page);

  await mockBackend(page);
  await openChat(page);
  await ask(page, "What does he do?");
  await stream.started();

  await stream.push(thought("knowledge_lookup"));
  await expect(page.getByText("Searching the CV…")).toBeVisible();

  await expect(page.getByLabel("Generating a reply")).toBeVisible();
  await expect(page.getByRole("status")).toHaveText("Generating a reply");
});

test("a failure clears the line, and a retry starts it again", async ({
  page,
}) => {
  const stream = await controlStream(page);

  await mockBackend(page);
  await openChat(page);
  await ask(page, "What does he do?");
  await stream.started();

  await stream.push(thought("knowledge_lookup"));
  await stream.push({ type: "error", message: "It broke." });
  await stream.end();

  await expect(page.getByText("It broke.")).toBeVisible();
  await expect(page.locator(".chat-progress")).toHaveCount(0);

  await page.getByRole("button", { name: /Try again/ }).click();

  await expect(page.getByText("Sending…")).toBeVisible();
});

test("a finished reply reloads with no line left on it", async ({ page }) => {
  const stream = await controlStream(page);

  await mockBackend(page);
  await openChat(page);
  await ask(page, "What does he do?");
  await stream.started();

  await stream.push(state("composing"));
  await stream.push({ type: "token", value: "Backend work." });
  await stream.push(doneFrame({ reply: "Backend work." }));
  await stream.end();

  await expect(page.getByLabel("Your question")).toBeEnabled();

  await page.reload();

  await expect(page.getByText("Backend work.")).toBeVisible();
  await expect(page.locator(".chat-progress")).toHaveCount(0);
});
