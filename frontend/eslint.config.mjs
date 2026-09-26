import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";

const eslintConfig = defineConfig([
  ...nextVitals,
  ...nextTs,
  // Override default ignores of eslint-config-next.
  globalIgnores([
    // Default ignores of eslint-config-next:
    ".next/**",
    "out/**",
    "build/**",
    "next-env.d.ts",

    // Build output, not source. `embed/` is linted; the bundle it produces is
    // a single minified line, and linting it is 1000 warnings about somebody
    // else's minifier.
    "public/embed.js",
  ]),
]);

export default eslintConfig;
