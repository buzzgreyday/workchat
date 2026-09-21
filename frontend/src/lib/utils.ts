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
