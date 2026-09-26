import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

/**
 * The version check, and why the real imports below are dynamic.
 *
 * Tailwind's node bindings use `module.isBuiltin`, which arrived in 18.6. On
 * anything older the failure is a linker error sixty lines into a minified
 * bundle, naming a symbol nobody here wrote and no file anybody here owns.
 *
 * A guard at the top of this file cannot prevent that: static imports are
 * linked before a single line of it runs, so the crash happens first. Loading
 * them on demand is what buys the chance to say something useful — which is
 * the whole reason this is not the ordinary import block it looks like it
 * should be.
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

const { build, context } = await import("esbuild");
const { default: postcss } = await import("postcss");
const { default: tailwindcss } = await import(
  "@tailwindcss/postcss"
);

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
 * Tailwind runs here rather than as a separate script.
 *
 * `globals.css` is source, not a stylesheet — `@import "tailwindcss"`, a
 * `@theme` block, `@apply` in the base layer. Handing that text to
 * `replaceSync` gets a shadow root full of at-rules the browser has no plugin
 * for, and `CSSStyleSheet` drops `@import` outright, so even the parts that
 * are real CSS would leave without saying goodbye.
 *
 * As a plugin rather than a build step because it keeps `--watch` honest: the
 * dependencies Tailwind reports are handed to esbuild, so editing a component
 * re-runs the scan that decides which utilities exist.
 */
const tailwind = {
  name: "tailwind",
  setup(esbuild) {
    esbuild.onLoad(
      { filter: /\.css$/ },
      async (args) => {
        const result = await postcss([
          tailwindcss(),
        ]).process(
          readFileSync(args.path, "utf8"),
          { from: args.path },
        );

        const files = [];
        const dirs = [];

        for (const message of result.messages) {
          if (message.type === "dependency") {
            files.push(message.file);
          } else if (
            message.type === "dir-dependency"
          ) {
            dirs.push(message.dir);
          }
        }

        return {
          contents: forShadowRoot(result.css),
          loader: "text",
          watchFiles: files,
          watchDirs: dirs,
        };
      },
    );
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

  plugins: [tailwind],
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
