/**
 * `embed.css` is imported for its text, not for its effect: esbuild's `text`
 * loader hands the compiled stylesheet over as a string, which the element
 * then adopts. TypeScript has no reason to expect that, so it is told.
 */
declare module "*.css" {
  const css: string;
  export default css;
}
