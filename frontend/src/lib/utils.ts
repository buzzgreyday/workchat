import { clsx, type ClassValue } from "clsx";
import { extendTailwindMerge } from "tailwind-merge";

/**
 * `clsx`, then a `tailwind-merge` that has been told about the scheme.
 *
 * The extension is not optional. tailwind-merge resolves conflicts from a
 * table of Tailwind's *default* scales, so a named token it has never heard of
 * — `size-control`, `rounded-card` — is not recognised as a member of its
 * group and cannot displace the `size-8` that `buttonVariants` contributes.
 * Both would survive into the class list and the winner would be decided by
 * Tailwind's internal sort order rather than by whoever wrote the component:
 * a 44px tap target silently becoming 32px.
 *
 * This list is the price of naming things. It is only consulted by `cn()`, and
 * `ui/button.tsx` is the only caller, so the blast radius is one component —
 * but a token added above and forgotten here fails quietly.
 */
const twMerge = extendTailwindMerge({
  extend: {
    theme: {
      color: [
        "canvas",
        "panel",
        "panel-raised",
        "line",
        "ink",
        "ink-muted",
        "accent",
        "on-accent",
      ],
      spacing: [
        "gutter-sm",
        "gutter",
        "gutter-lg",
        "control",
        "composer-max",
      ],
      radius: ["control", "bubble", "card"],
      text: ["title", "body", "meta", "micro"],
      container: ["chat"],
    },
  },
});

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

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
