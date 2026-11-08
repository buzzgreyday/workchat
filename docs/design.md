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
| **Muted text** — sage | `#809e85` | Placeholders, footer links, secondary labels. A grey tinted green. |
| **Accent** — blue-grey | `#94b4c1` | Links in text. Tints the visitor's own messages (`#4e6778`, 45% accent into navy). |
| **Identity** — pale gold | `#e0cea1` | The WORKCHAT title, status text such as "questions left". Who this is and where you are. |
| **Action** — coral | `#e0876a` | The one thing to press: the send button. Nothing else. |
| Icon on action | `#1b2e42` | The navy, on coral. |
| Borders | `#ffffff` at 10% | Hairlines between parts and around raised surfaces. |
| Focus | `#675255` | Input border on focus: coral mixed 40% into navy, so focus shows without glaring. |

Rules that keep it coherent:

- **Coral means "press this".** One coral thing per view. Using it for
  decoration or headings takes the meaning away from the button.
- **Pale gold means "this is Michael's".** Titles, status. It is
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
| Sage muted text on navy | 4.7:1 |
| Sage muted text on raised surface | 3.8:1 |

The muted text was a neutral grey (`#86898f`), at 3.95:1 on navy and 3.2:1
on the raised surface: excused as small print, and below the guideline for
anything read. Sage is the same lightness tinted green, and the tint alone
moves it far enough from the navy to pass 4.5:1 there. A dark green was
tried first and rejected: at 1.8:1 it cannot be read.
On the raised surface it is still below 4.5:1, so placeholders and the pill's
count stay short labels, not sentences.

## Type

| Role | Face | Weight | Size |
| --- | --- | --- | --- |
| Title | **Bebas Neue** | 800 on chat.mringdal.com; 600 in the embed unless the host sets `--chat-font-title-weight`. Either is faked: 400 is its only weight, capitals only | 2.5rem, down to 1.5rem on a phone |
| Messages | **Nunito** | 400 | 1.125rem, line height 1.5. 300 was too thin to read on the navy. |
| Small labels | Nunito | 400 | 0.875rem (links, pills) |

- Bebas has one weight. Anything above 400 is a bold the browser fakes; beyond that, use size for emphasis, not weight.
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
| Message bubbles | 14px on every corner, like the controls |
| Pills | fully round |
| Gutters | 16px (phone, tight), 20px, 24px (roomy) |
| Controls | 50px tall or a little over, with the text — a one-line input and its button match. Never under 44px: a tap target. |
| Reading width | 56rem (896px) at most |
| Buttons | One kind, `.button`, in each project. Its colour down to a slightly darker foot, under four shadows, as if lit from above: a 1px inset of light along the top, a 2px inset of dark along the bottom, a tight shadow where it meets the page, and a soft glow beneath in its own colour. The gradient, the dark edge and both shadows are darker versions of the colour, lightness only, so they suit any host and the darkest edge is never grey. Hover barely brightens and does not move; pressed, it goes flat, moves down 1px and takes a dark inset shadow in its own colour. Disabled is flat, with no shadow. |
| Shadows | A tight one at the contact and a wide soft one around it, on pills. Bubbles add a faint inner glow along the top, and stay quieter than buttons. Inputs are sunk, with an inset. |
| Avatars | None. The bubbles' sides say who is speaking. |
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
| `app/styles/buttons.css` | `.button`, the one kind of button |
| `app/styles/chat.css` | The `--chat-*` variables, on the `workchat-chat` element, and the chat window: its bar, its ring, and what it draws on the element's parts |

One thing it does differently from chat.mringdal.com, on purpose: **body text
is Nunito at 600**, not 400, and bold needs 800 to read as bold. Its body text
is 1.125rem, the size of the chat's own messages, and it tells the embedded
messages the same.

The faces are loaded in the page, so their variables inherit into the chat's
shadow root and its `@font-face` rules are the document's, where the shadow root
can use them. The element sets no `--chat-font`: it inherits the page's. The
palette is handed over on the element rather than `:root`, because the element
declares its own defaults on `:host` and an inherited value loses to those. The
chat window draws its own bar, so the chat is told `header="none"`. `EMBED.md`
lists every `--chat-*` variable the element reads.

### The chat window

A window over the homepage, in the corner on a wide screen and the whole
screen on a phone. What it does differently from chat.mringdal.com, through
the element's `--chat-*` variables, its parts and its `working` state
(`EMBED.md`):

| | |
| --- | --- |
| The window | Solid navy, with no box or card of the chat's own in it. |
| A question | Raised: the raised surface at 80%, a hairline round it and a faint light along its top, with half a line more room above and below than between messages. |
| A reply | Plain text, no bubble — the page's reading, not a message in a box. Its paragraphs a gap apart. |
| The margins | One line down the left, 1rem in: the questions left, the replies, the box to type in. |
| The scrollbar | None, through the element's `scrollbar="none"`. The conversation still scrolls, by wheel, touch and keys. |
| Scrolling | A question goes to the top, and its reply arrives under it with the view held still. Once the reply runs past the foot, a round button there goes to the end: flat, the raised surface with a sage arrow, like the way out. |
| Questions left | Plain sage text at the start of the bar, opposite the way out. |
| Send | Round, coral, inside the box to type in at its end: the one thing in the window to press. An arrow up, paired with the arrow down to the latest. |
| Close | Round, the raised surface with a sage ×: the quietest way out. |
| Round buttons | Send, close and the button to the latest share one 3D, so slight it is almost not there: a faint light high on the circle, a little shade low on it, a soft shadow under it. The site's full press is for its large buttons. |
| The ring | Round the box to type in, a hairline of two colours drifting over each other with a glint of light. Listening, the sage, slowly. Working — opening its session, writing a reply — a violet and a magenta, fast. One fades into the other over a second. |

Violet `oklch(0.72 0.13 300)` and magenta `oklch(0.74 0.13 350)` are the
window's own, and say only "the chat is at work". Listening takes no colour of
its own: it is the sage the window already uses for its quiet marks, so
waiting is the window at rest rather than a signal.

| Pair | Contrast |
| --- | --- |
| Sage × on the raised surface | 3.8:1 — an icon, against 3:1 |
| Navy icon on coral | 5.2:1 |

Tried and taken out, so they are not tried again for the same reasons:

- **Glass.** The window and the chat in it see-through, the page frosted
  behind. Over the homepage the coral and the gold came through as muddy
  smears, and on a phone, with the page hidden behind the chat, it was navy
  over navy.
- **A glow for the state.** Under the window, then a band along its foot, in
  lemon, green-blue, aqua and sky blue. Behind the navy a lemon went olive;
  on the glass the band sat mostly behind the box to type in; and saying the
  state by pace more than by colour, it did not read as a state at all. The
  ring is on the box, where the visitor looks.
- **A bright listening ring**, aqua and sky blue: a light always on.
- **Two coral buttons.** Two "press me"s in one small window, and the way out
  pulled the eye as hard as the thing it was there for. A sage close button
  came after it, and was one colour too many beside send.
- **The count as a pill** in the pale gold: one more raised thing in the bar,
  saying "look here" about a number that only needs to be findable.

## Trying changes

The Workchat Theme Lab (an artifact in Claude, private to its owner) shows
the chat with a picker for every colour and font in `theme.css`, contrast
checks, and the lines to paste back. Settle a change there, apply it to
`theme.css`, then update the tables above.
