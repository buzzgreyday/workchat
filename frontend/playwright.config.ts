import { defineConfig, devices } from "@playwright/test";

const PORT = 3100;

/**
 * End-to-end tests for the chat page.
 *
 * The backend is mocked at the network boundary rather than run for real, and
 * that is the point rather than a shortcut. What these tests are about is
 * frontend behaviour the type checker cannot see — a composer that stays dead
 * after a failed reply, a transcript that does or does not survive a reload —
 * and producing those states against a live backend would mean a database, an
 * OpenAI key, and a way to make a real model fail on demand. The backend's own
 * contract is covered by its 191 pytest cases.
 *
 * Tests run against `next start`, not `next dev`: the owner configuration is
 * read on the server during dynamic rendering, and a production build is where
 * that claim is worth checking.
 */
export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 2 : 0,
  // Annotations inline on the PR, plus an HTML report CI uploads when a run
  // fails — a trace is worth far more than a log line for a browser test.
  reporter: process.env.CI
    ? [["github"], ["html", { open: "never" }]]
    : [["list"]],

  use: {
    baseURL: `http://127.0.0.1:${PORT}`,
    trace: "on-first-retry",
  },

  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
    // A phone, because every fault this project exists to catch is one that a
    // 1280px window cannot show: a document 2rem taller than the screen, a
    // white canvas behind it, a placeholder that wraps inside a one-row box.
    // All three shipped, and the desktop suite passed the whole time.
    //
    // Pixel 5 is a chromium descriptor, so this costs no second browser
    // download — `playwright install chromium` in CI already covers it, and
    // the suite stays what the README says it is rather than turning into a
    // compatibility matrix.
    {
      name: "mobile",
      use: { ...devices["Pixel 5"] },
    },
  ],

  webServer: {
    // The standalone server, which is what the Dockerfile runs — `next start`
    // warns that it does not support `output: "standalone"`, and the thing
    // being asserted here is precisely how the production server reads its
    // environment. The copy steps mirror the Dockerfile's COPY lines.
    //
    // Builds as well as serves, and NEXT_PUBLIC_API_URL is baked by that
    // build. It has to be the relative "/api": with an absolute backend URL
    // every mocked call becomes cross-origin, and the browser would demand a
    // CORS preflight that a fulfilled route does not answer.
    command:
      "npm run build:standalone && node .next/standalone/server.js",
    url: `http://127.0.0.1:${PORT}`,
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
    env: {
      PORT: String(PORT),
      HOSTNAME: "127.0.0.1",
      NEXT_PUBLIC_API_URL: "/api",
      NEXT_TELEMETRY_DISABLED: "1",
      // Set here so the suite can prove the header follows the environment of
      // the running server rather than whatever was baked at build time.
      OWNER_NAME: "Ada Lovelace",
      OWNER_GITHUB_URL: "https://github.com/ada",
      // Explicitly empty: an owner with no LinkedIn must get no link, not the
      // author's.
      OWNER_LINKEDIN_URL: "",
    },
  },
});
