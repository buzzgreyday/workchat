import { expect, test } from "@playwright/test";

import {
  gate,
  mockBackend,
  openChat,
} from "./backend";

/**
 * What the page says before it knows who is reading.
 *
 * A claim link costs a round trip before it knows the hirer's name, and the
 * greeting used to fill that gap with a bare "Hi! 👋" addressed to nobody,
 * then flip to their name once the exchange landed.
 *
 * The v1 half of this — a link that *is* the token, so the greeting lands on
 * the first paint — moved to `legacy.spec.ts` with the rest of `?token=`.
 */

test("a claim link shows it is working, then greets by name", async ({
  page,
}) => {
  // Hold the exchange open so the loading state is observable rather than a
  // race — this is precisely the window the greeting used to get wrong. This
  // used to be hand-rolled here, re-declaring the whole session response body
  // just to delay it; the mock takes the promise now.
  const { held, release } = gate();

  await mockBackend(page, {
    sub: "Grace Hopper",
    holdClaim: held,
  });

  await openChat(page);

  await expect(
    page.getByLabel("Generating a reply"),
  ).toBeVisible();
  await expect(
    page.getByText("Hi!", { exact: true }),
  ).toHaveCount(0);

  release();

  await expect(
    page.getByText("Hi Grace Hopper! 👋"),
  ).toBeVisible();

  // The dots must not linger behind the text — the greeting carries a status
  // as well as content, and forgetting that left it streaming forever.
  await expect(
    page.getByLabel("Generating a reply"),
  ).toHaveCount(0);
});
