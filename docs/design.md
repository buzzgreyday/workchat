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
| **Surface** — navy | `#1b2e42` | The page and everything on it: the top bar, the chat band, the footer, cards. One colour, no frame of another around it. |
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
- **Two surfaces, not three:** navy, then raised. The bars are the page's
  navy with no line under or over them, so the title and links float on it.
  Nothing lighter than the raised surface sits on navy except text and the two
  signal colours.
- **No steel blue.** It framed the page once (`#547792`) and read as
  corporate; mringdal.com keeps it only for its story's headings.

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
| Pale gold title on navy | 8.9:1 |

Muted text on navy (the footer links, the trial notice) is 4.0:1: fine
for small print, not for anything someone has to read to use the page.

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

In a Next.js project, load them with `next/font/google` instead,
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
| Motion | Named `--motion-*` durations, each project its own. Anything that moves holds still under `prefers-reduced-motion: reduce` |

Layout on chat.mringdal.com: a full-width top bar, the content edge to edge
with a centred reading column, and a slim footer with the profile links — all
the one navy, with no lines between them, as mringdal.com draws its own page.

## On mringdal.com (Next.js + plain CSS)

The website already uses this scheme, in plain CSS. Its own files are the
reference, rather than a copy here that could drift from them:

| File, in `mringdal-site` | Holds |
| --- | --- |
| `app/layout.tsx` | The two faces, through `next/font/google` |
| `app/styles/tokens.css` | The colours, faces, radii and motion, on `:root` |
| `app/styles/base.css` | `html` and `body`: the navy, the cream and the body type |
| `app/styles/buttons.css` | `.action`, the one thing to press on a view |
| `app/styles/chat.css` | The `--chat-*` variables, on the `workchat-chat` element |

Three things it does differently from chat.mringdal.com, on purpose:

- **Body text is Nunito at 600**, not 300, and bold needs 800 to read as bold.
- **Its titles ask Bebas for 800**, a weight the browser fakes.
- **The site's boxes round at 14px**: the story box and the chat window, with
  the buttons. The chat's own bubbles stay 18px.

The faces are loaded in the page, so their variables inherit into the chat's
shadow root and its `@font-face` rules are the document's, where the shadow root
can use them. The element sets no `--chat-font`: it inherits the page's. The
palette is handed over on the element rather than `:root`, because the element
declares its own defaults on `:host` and an inherited value loses to those. The
chat window draws its own bar, so the chat is told `header="none"`. `EMBED.md`
lists every `--chat-*` variable the element reads.

## Trying changes

The Workchat Theme Lab (an artifact in Claude, private to its owner) shows
the chat with a picker for every colour and font in `theme.css`, contrast
checks, and the lines to paste back. Settle a change there, apply it to
`theme.css`, then update the tables above.
