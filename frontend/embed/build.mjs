import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { build, context } from "esbuild";

/**
 * The same floor as Next and the Dockerfile, said plainly rather than left to
 * whichever dependency trips over it first.
 */
const MINIMUM_NODE = 20;

if (
  Number(process.versions.node.split(".")[0]) <
  MINIMUM_NODE
) {
  console.error(
    [
      `The embed build needs Node ${MINIMUM_NODE} or newer.`,
      `This is Node ${process.versions.node}.`,
      "",
      "Same floor as Next and the Dockerfile. `nvm use` reads .nvmrc.",
    ].join("\n"),
  );

  process.exit(1);
}


/**
 * The element, as one file the site can load at runtime.
 *
 * Output goes to `public/embed.js`, so the deployed chat serves it at
 * /embed.js. That is the whole delivery mechanism: the site has a script tag,
 * this deployment decides what is behind it, and a release here reaches the
 * site on its next page load without anything being rebuilt there.
 *
 * Bundled, not split: a single request, no chunk paths to keep stable across
 * releases, and nothing for a stale HTML page to point at.
 *
 * Run from `frontend/`, via `npm run build:embed`, and paths here are resolved
 * against this file rather than the working directory so that stays true
 * wherever it is invoked from.
 */
const here = (path) =>
  fileURLToPath(new URL(path, import.meta.url));

/**
 * `:root` never matches inside a shadow root — the root there is the shadow
 * root itself, which is `:host`. Every custom property in `globals.css` is
 * declared on `:root`, so without this the sheet lands intact and resolves to
 * nothing: no palette, no radii, no fonts.
 *
 * Rewritten to a list rather than replaced, so the compiled sheet keeps
 * working if it is ever loaded into a document. `:host` is valid syntax
 * outside a shadow tree — it simply matches nothing — and an invalid selector
 * would take the whole rule down with it.
 */
const forShadowRoot = (css) =>
  css.replace(/(?<![\w-]):root\b/g, ":host, :root");

/**
 * What the sheet is written down for: esbuild adds the prefixes these still need
 * (`-webkit-user-select`, for one) and rewrites what they cannot read. Every
 * iPhone browser is Safari underneath, which is the one that matters here.
 */
const CSS_TARGET = ["safari16.4", "chrome111", "firefox128"];

/**
 * The stylesheet, joined here rather than as a separate script.
 *
 * `embed.css` imports `globals.css`, which imports the rest. Handing that text
 * to `replaceSync` would lose them: `CSSStyleSheet` drops `@import` outright. So
 * a CSS file is built on its own into one sheet, and arrives in the bundle as a
 * string, for the shadow root to adopt.
 *
 * As a plugin rather than a build step because it keeps `--watch` honest: the
 * files that went into the sheet are handed to esbuild to watch.
 */
const stylesheet = {
  name: "stylesheet",
  setup(esbuild) {
    esbuild.onLoad({ filter: /\.css$/ }, async (args) => {
      const result = await build({
        entryPoints: [args.path],
        bundle: true,
        minify: true,
        write: false,
        target: CSS_TARGET,
        metafile: true,
        outdir: here("../public"),
      });

      return {
        contents: forShadowRoot(result.outputFiles[0].text),
        loader: "text",
        watchFiles: Object.keys(result.metafile.inputs).map((file) =>
          resolve(file),
        ),
      };
    });
  },
};

const options = {
  entryPoints: [here("src/element.tsx")],
  bundle: true,
  format: "esm",
  target: "es2022",
  outfile: here("../public/embed.js"),
  minify: true,

  // No source map. It would be written next to the bundle in `public/`, which
  // is to say published — the whole app's source, served to anyone who asks
  // for /embed.js.map. Debugging a release is worth less than that.
  sourcemap: false,

  jsx: "automatic",

  // The app's own, so `@/*` resolves here exactly as it does under Next.
  tsconfig: here("../tsconfig.json"),

  plugins: [stylesheet],
  define: {
    "process.env.NODE_ENV": '"production"',

    // Next substitutes this at compile time; esbuild does not, and a bare
    // `process` in a browser is a ReferenceError on the first line that runs.
    // Defined away to `undefined` so `api.ts` falls through to its default,
    // which the element then overrides from `api-url` before anything is sent.
    "process.env.NEXT_PUBLIC_API_URL": "undefined",
  },
  banner: {
    js: `/* workchat embed ${JSON.parse(readFileSync(here("../package.json"), "utf8")).version ?? "0.0.0"} */`,
  },
};

if (process.argv.includes("--watch")) {
  const ctx = await context(options);
  await ctx.watch();
  console.log("watching");
} else {
  await build(options);
  console.log("built public/embed.js");
}
