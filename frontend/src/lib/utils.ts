/**
 * A random id for a transcript entry.
 *
 * Not a bare `crypto.randomUUID()`: browsers only define it in a secure
 * context, which is HTTPS or localhost. Anywhere else — a phone opening the
 * dev server by its LAN address, a host page served over plain http — it is
 * undefined, and asking a question threw before anything was sent.
 * `getRandomValues` has no such restriction, so the fallback builds the same
 * version-4 shape from it.
 */
export function newId(): string {
  if (typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }

  const bytes = crypto.getRandomValues(new Uint8Array(16));

  // RFC 4122: version 4, variant 10xx. `?? 0` only for the index check:
  // the array is 16 long, so both are always there.
  bytes[6] = ((bytes[6] ?? 0) & 0x0f) | 0x40;
  bytes[8] = ((bytes[8] ?? 0) & 0x3f) | 0x80;

  const hex = Array.from(bytes, (byte) =>
    byte.toString(16).padStart(2, "0"),
  ).join("");

  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}
