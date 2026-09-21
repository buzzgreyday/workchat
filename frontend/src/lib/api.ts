/**
 * Where the backend is.
 *
 * Was written out three times, once in each service, which is three places to
 * change and three chances to change two of them. Baked into the bundle at
 * build time — `NEXT_PUBLIC_*` is substituted by the compiler, not read at
 * runtime — so it belongs to the image, and the fallback is only ever the
 * developer running `next dev` against a local backend.
 */
export const API_URL =
  process.env.NEXT_PUBLIC_API_URL ??
  "http://localhost:8000";
