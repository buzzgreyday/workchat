/**
 * Where the backend is.
 *
 * Was written out three times, once in each service, which is three places to
 * change and three chances to change two of them.
 *
 * Two answers, because there are two deliveries. The app itself is a Next
 * build, where `NEXT_PUBLIC_*` is substituted by the compiler and the value
 * belongs to the image. The embed is one file served to somebody else's page,
 * built once and loaded by hosts this deployment has never heard of — nothing
 * about it can be baked at build time, so `<workchat-chat api-url="...">`
 * calls `setApiUrl` before it renders and that wins.
 *
 * Read through `apiUrl()` rather than exported as a constant: a constant is
 * captured at import, and the element sets the override after these modules
 * have been imported but before any request is made.
 */
const BUILD_TIME_URL =
  process.env.NEXT_PUBLIC_API_URL ??
  "http://localhost:8000";

/**
 * Module scope, so it is per bundle rather than per element. Two
 * `<workchat-chat>` elements on one page share it — they are the same chat
 * talking to the same backend, and giving them different values is not a case
 * worth carrying state for.
 */
let runtimeUrl: string | null = null;

export function setApiUrl(url: string): void {
  runtimeUrl = url;
}

export function apiUrl(): string {
  return runtimeUrl ?? BUILD_TIME_URL;
}
