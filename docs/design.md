# The mringdal look

The design of chat.mringdal.com, written down so other projects — the
mringdal.com website first (Next.js, the `mringdal-site` repo) — can use the
same colours, type and shapes without reading this repo's CSS.

**Source of truth:** `frontend/src/app/theme.css`. The hex values below are
what the browser renders from it today (several are mixes). If `theme.css`
changes, update this file with it.

## Colour

Four roles, and each colour has one job. Keeping the jobs apart is what makes
the page readable at a glance.

| Role | Hex | Used for |
| --- | --- | --- |
| **Frame** — steel blue | `#547792` | The page itself: top bar, footer, anything around the content. |
| **Surface** — navy | `#1b2e42` | Where the content sits: the chat band, cards. |
| **Raised surface** | `#2b3d4f` | Things on the surface: reply bubbles, the input, pills. The navy lifted with 8% white. |
| **Text** — cream | `#eae0cf` | All body text. |
| **Muted text** | `#86898f` | Placeholders, footer links, secondary labels. |
| **Accent** — blue-grey | `#94b4c1` | Links in text. Tints the visitor's own messages (`#4e6778`, 45% accent into navy). |
| **Identity** — pale gold | `#e0cea1` | The WORKCHAT title, the avatar dot, status text such as "questions left". Who this is and where you are. |
| **Action** — coral | `#e0876a` | The one thing to press: the send button. Nothing else. |
| Icon on action | `#1b2e42` | The navy, on coral. |
| Borders | `#ffffff` at 10% | Hairlines between parts and around raised surfaces. |
| Focus | `#675255` | Input border on focus: coral mixed 40% into navy, so focus shows without glaring. |

Rules that keep it coherent:

- **Coral means "press this".** One coral thing per view. Using it for
  decoration or headings takes the meaning away from the button.
- **Pale gold means "this is Michael's".** Titles, the avatar, status. It is
  never a button.
- **Text is cream, not white.** Pure white is harsher than the rest of the
  palette.
- **Surfaces step up in lightness:** frame, then navy, then raised. Nothing
  lighter than the raised surface sits on navy except text and the two
  signal colours.

### Readability

Measured contrast. 4.5:1 is the guideline for body text, 3:1 for large text
(the title) and for buttons and icons.

| Pair | Ratio |
| --- | --- |
| Cream text on raised surface | 8.5:1 |
| Cream text on the visitor's message | 4.5:1 |
| Pale gold status text on its pill | 7.2:1 |
| Coral button against navy | 5.2:1 |
| Navy icon on coral | 5.2:1 |
| Pale gold title on steel blue | 3.0:1 — large text only, and at the limit: lighten the gold rather than darken it |

Muted text on steel blue (the footer links) is low. Keep it to small print
nobody needs to read.

## Type

| Role | Face | Weight | Size |
| --- | --- | --- | --- |
| Title | **Bebas Neue** | 400 (its only weight; capitals only) | 2.5rem, down to 1.5rem on a phone |
| Body, messages | **Nunito** | 300 (light) | 1rem, line height 1.5 |
| Small labels | Nunito | 300 | 0.875rem (links), 0.75rem (pills) |

- Bebas has one weight. Asking for more makes the browser fake a bold; use
  size for emphasis instead.
- Write the title in normal case. Bebas draws capitals anyway, and screen
  readers spell out text typed in capitals.
- Any text field on a phone must be at least 16px, or iOS zooms the page when
  it takes focus.

Both faces are on Google Fonts under the OFL, so any project can load them:

```html
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Bebas+Neue&family=Nunito:wght@300;400;600&display=swap" rel="stylesheet">
```

In a Next.js project, load them with `next/font/google` instead (below),
which serves them from your own domain. Use the Google copies either way:
the Fontshare downloads of Bebas (and Sentient) in
this repo's working folder are under a licence that forbids putting them in a
public repository.

## Shape and space

| | Value |
| --- | --- |
| Base radius | 10px |
| Buttons, inputs | 14px |
| Message bubbles | 18px, with the corner nearest the speaker at 6px |
| Pills | fully round |
| Gutters | 16px (phone, tight), 20px, 24px (roomy) |
| Controls | 50px tall — a one-line input and its button match. Never under 44px: a tap target. |
| Reading width | 56rem (896px) at most |
| Shadows | Small only: `0 1px 3px rgb(0 0 0 / 0.1)` on bubbles, pills and the button |

Layout on chat.mringdal.com: a full-width top bar in the frame colour, the
content in a navy band edge to edge with a centred reading column, and a
slim footer in the frame colour with the profile links.

## Using it on mringdal.com (Next.js + Tailwind 4)

The website already has the right structure: a few tokens on `:root` in
`app/globals.css`, applied to `html` and `body`, and handed to the embedded
chat on the `workchat-chat` element. Its values are placeholders. Three
steps replace them with this scheme.

### 1. Fonts, in `app/layout.tsx`

```tsx
import { Bebas_Neue, Nunito } from "next/font/google";

const nunito = Nunito({
  variable: "--font-nunito",
  subsets: ["latin"],
  weight: ["300", "400", "600"],
});

const bebas = Bebas_Neue({
  variable: "--font-bebas",
  subsets: ["latin"],
  weight: "400",
});

// on <html>:
// className={`${nunito.variable} ${bebas.variable}`}
```

The variables are set on `<html>` and inherit into the chat's shadow root,
and next/font's `@font-face` rules live in the document, where the shadow
root can use them. So loading the fonts here also makes them available to
the embedded chat (step 3).

### 2. Tokens, in `app/globals.css`

The existing names stay, so nothing that already reads them changes. The page
is navy with cream text; the steel blue frames it (header, footer).

```css
@import "tailwindcss";

:root {
  --frame: #547792;
  --bg: #1b2e42;
  --surface: #2b3d4f;
  --line: rgb(255 255 255 / 0.1);
  --text: #eae0cf;
  --muted: #86898f;
  --accent: #94b4c1;
  --identity: #e0cea1;
  --action: #e0876a;
  --on-action: #1b2e42;
}

/* Utilities: bg-frame, bg-surface, text-identity, bg-action, font-display… */
@theme inline {
  --color-frame: var(--frame);
  --color-canvas: var(--bg);
  --color-surface: var(--surface);
  --color-line: var(--line);
  --color-ink: var(--text);
  --color-ink-muted: var(--muted);
  --color-accent: var(--accent);
  --color-identity: var(--identity);
  --color-action: var(--action);
  --color-on-action: var(--on-action);

  --font-sans: var(--font-nunito), ui-sans-serif, system-ui, sans-serif;
  --font-display: var(--font-bebas), "Arial Narrow", sans-serif;

  --radius-control: 14px;
  --radius-bubble: 18px;
}

html,
body {
  background: var(--bg);
  color: var(--text);
}

body {
  font-family: var(--font-sans);
  font-weight: 300;
  line-height: 1.5;
}
```

`@theme inline` rather than plain `@theme`, so the utilities read the
variables at run time and a change on `:root` reaches them. The theme key
and the next/font variable must have different names (`--font-sans` reads
`--font-nunito`): a variable that reads itself is a cycle and computes to
nothing.

Headings then take `font-display text-identity`, the one call to action on a
page `bg-action text-on-action rounded-control`, and cards
`bg-surface border border-line rounded-bubble`.

### 3. The embedded chat, in the same file

Replace the `workchat-chat` block. It gives the chat the site's colours and
fonts, set up the way chat.mringdal.com is:

```css
workchat-chat {
  --chat-bg: var(--frame);
  --chat-panel: var(--bg);
  --chat-panel-alt: var(--surface);
  --chat-border: var(--line);
  --chat-text: var(--text);
  --chat-text-muted: var(--muted);
  --chat-accent: var(--accent);

  --chat-title-color: var(--identity);
  --chat-avatar-bg: var(--identity);
  --chat-avatar-icon-display: none;
  --chat-badge-text: var(--identity);
  --chat-user-bubble-bg: color-mix(in oklab, var(--accent) 45%, var(--bg));
  --chat-send-bg: var(--action);
  --chat-send-icon: var(--on-action);
  --chat-input-focus: color-mix(in oklab, var(--action) 40%, var(--bg));

  --chat-font: var(--font-nunito), ui-sans-serif, system-ui, sans-serif;
  --chat-font-weight: 300;
  --chat-font-title: var(--font-bebas), "Arial Narrow", sans-serif;
  --chat-font-title-weight: 400;
}
```

The dialog shows the chat with `header="none"` and draws its own header, so
style that header with the page's tokens: the title in `font-display
text-identity`, the questions-left count in `text-identity`. `EMBED.md` lists
every `--chat-*` variable the element reads.

## Trying changes

The Workchat Theme Lab (an artifact in Claude, private to its owner) shows
the chat with a picker for every colour and font in `theme.css`, contrast
checks, and the lines to paste back. Settle a change there, apply it to
`theme.css`, then update the tables above.
