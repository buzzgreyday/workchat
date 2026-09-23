import { spawn } from "node:child_process";
import { existsSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { resolve } from "node:path";

/**
 * Run the site's tests against the element this repo just built.
 *
 * The contract between the two projects is unpinnable by design — the site
 * loads `/embed.js` at runtime and there is no version to hold back — so the
 * only thing that can catch it moving is the consumer's own suite, run against
 * a fresh bundle. That is what this does, and it belongs here rather than
 * there: the site cannot break the contract, and this repo can.
 *
 * The backend stays mocked. What is being checked is the element's surface —
 * the attributes, the event, the shadow root, the `--chat-*` variables — and a
 * live backend would only add a database and a key to a question that does not
 * involve either.
 *
 *   npm run test:contract
 *   WEBSITE_DIR=../elsewhere npm run test:contract
 */
const here = (path) =>
  fileURLToPath(new URL(path, import.meta.url));

const website = resolve(
  process.env.WEBSITE_DIR ?? here("../../../website"),
);

const bundle = here("../public/embed.js");

if (!existsSync(bundle)) {
  console.error(
    `No bundle at ${bundle}. Run \`npm run build:embed\` first.`,
  );
  process.exit(1);
}

if (!existsSync(resolve(website, "playwright.config.ts"))) {
  console.error(
    [
      `No site checkout at ${website}.`,
      "",
      "It is a separate repository and this one does not depend on it, so",
      "there is nothing to install — clone it beside this repo, or point",
      "WEBSITE_DIR at it:",
      "",
      "  WEBSITE_DIR=/path/to/website npm run test:contract",
    ].join("\n"),
  );
  process.exit(1);
}

if (!existsSync(resolve(website, "node_modules"))) {
  console.error(
    `${website} has no node_modules. Run \`npm install\` there first.`,
  );
  process.exit(1);
}

console.log(`Running the site's suite against ${bundle}\n`);

const run = spawn("npm", ["run", "test:e2e"], {
  cwd: website,
  stdio: "inherit",
  env: { ...process.env, CHAT_EMBED_JS: bundle },
});

run.on("exit", (code) => process.exit(code ?? 1));
