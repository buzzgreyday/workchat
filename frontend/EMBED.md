# Embedding workchat

The chat is published as a custom element from this deployment. A page adds a
script tag and an element; there is no package to install and no version to
pin, so a release here reaches every embedding page on its next load.

```html
<script type="module" src="https://chat.mringdal.com/embed.js"></script>

<workchat-chat
  api-url="https://api.mringdal.com"
  style="height: 100%"
></workchat-chat>
```

## The API

Versioned like an API, because it is one — and unlike a package, nobody can
stay behind on an old version. Adding an attribute, an event or a variable is
safe. Renaming or removing one breaks every page that embeds this.

**Attributes**

| Attribute | Meaning |
| --- | --- |
| `api-url` | Where the backend is. Defaults to `/api`. |
| `about` | Opens the composer with this question in it, unsent. |
| `claim` | A claim token, when the visitor followed a link. |
| `owner-name` | Whose CV this is. Defaults to the name in `lib/owner-defaults.ts`. |
| `header` | `none` hides the chat's header — its title and the questions-left badge. Anything else, or nothing, shows it. |

The app reads the owner from the environment during its server render. An
embed has no server render, so the host page says who this is — or says
nothing and gets the default.

`owner-github` and `owner-linkedin` are gone. The links moved out of the chat
onto the standalone page, below the card, because an embedding page already
has its own way of pointing at its owner. Setting them does nothing now, and
breaks nothing: an attribute the element does not read is ignored.

`about` seeds the composer rather than asking: the visitor reads it, edits it
or deletes it, and a handful of questions is too few to spend one on wording
nobody saw. It is read on the element's first render, so set it in the markup
or before the element is inserted — React does the latter by itself. Changing
it later does not re-seed, which is what stops it overwriting what somebody is
halfway through typing.

`header="none"` is for a host that frames the chat with a header of its own,
such as a dialog with a title and a close button. The allowance the badge
would have shown still arrives, as `workchat-usage`; show it wherever the
host's header has room.

**Events** (bubbling and composed, so listen on the element)

| Event | Detail |
| --- | --- |
| `workchat-usage` | `{ used, remaining, max }` |

There is no close event. Running in the host's document, Escape reaches their
`<dialog>` on its own — forwarding it was something only a frame needed.

**CSS variables** — the palette is the `--chat-*` set declared at the top of
`src/app/globals.css`: `--chat-bg`, `--chat-panel`, `--chat-border`, and the
rest. Its values are plain defaults, not the standalone site's look, which
lives in `src/app/theme.css` and never reaches an embed. Set them on the
element itself:

```css
workchat-chat {
  --chat-bg: #0b1020;
  --chat-accent: #7c5cff;
}
```

A rule the host page writes for the element outranks the element's own
`:host` defaults, so this needs nothing passed and no protocol to maintain.
Set them on an ancestor instead and the defaults inside win, because custom
properties inherit but are then overridden by the shadow tree's own
declaration — the element is the place to put them.

**Fonts** — by default the chat is in the host page's font: it inherits, like
any other text on the page. To choose, set these on the element too:

| Variable | Meaning | Unset |
| --- | --- | --- |
| `--chat-font` | The text's font family. | The host's font. |
| `--chat-font-weight` | The text's weight. | The host's weight. |
| `--chat-font-title` | The header title's family. | `--chat-font`. |
| `--chat-font-title-weight` | The title's weight. | `600` |
| `--chat-font-title-size` | The title's size. | `1.25rem` |

```css
workchat-chat {
  --chat-font: "Inter", system-ui, sans-serif;
  --chat-font-title: "Fraunces", serif;
}
```

The host loads the font, not the element. An `@font-face` inside a shadow
root is ignored, so a face has to be declared in the host's document — its
stylesheet, a Google Fonts link, next/font — and the variables name it. Give
the family a fallback stack, as above; the element adds none of its own.

**Sizing** — the element fills its container and sets no height of its own
beyond `100%`. Give the container one, or give the element one, or it
collapses.

Its layout responds to the space it is given, not to the window. The card
caps at 700px tall once the chat is 40rem wide, and fills its container when
narrower — so a chat in a small dialog on a large screen fills the dialog, as
it would on a phone.

## Building

```bash
cd frontend && npm install && npm run build:embed
```

Writes `frontend/public/embed.js`, which the deployment serves at `/embed.js`.
`npm run build` builds it before `next build`, and `build:standalone` goes
through `npm run build`, so a deploy cannot ship an HTML change without the
matching element. `npm run watch:embed` rebuilds on change, components
included — the Tailwind scan is part of the bundle graph.

There is no separate install for the embed: it builds with the app's own
esbuild, Tailwind and React, against the app's `tsconfig.json`. One React, one
Tailwind, one version of the chat. Needs Node 20+, same as Next.

The stylesheet is compiled, not copied. `embed/src/embed.css` imports
`globals.css`, Tailwind runs over it inside the esbuild plugin, and `:root` is
rewritten to reach `:host` — inside a shadow root there is no `:root` to
declare a palette on. The result is adopted by the shadow root, so the host
page's stylesheets are untouched in both directions.

## Testing it with the site

The contract is unpinnable by design: the site loads `/embed.js` at runtime and
has no version to hold back on. So the only thing that can catch it moving is
the site's own suite, run against a bundle from here.

```bash
npm run test:contract                        # ../website
WEBSITE_DIR=/path/to/site npm run test:contract
```

Builds the element and runs the site's Playwright tests against that exact
file. Rename an attribute, an event or a `--chat-*` variable and it goes red
here, in this repo, before the change is deployed to a site that cannot pin a
version of it. It needs a checkout of the site with its dependencies
installed, and nothing else — no database, no key, no stack. The backend stays
mocked, because what is being checked is this element's surface.

The site keeps its own copy of the contract in `types/workchat.d.ts` and a
stand-in element in `e2e/fixtures/`. When the stand-in passes and the real
bundle does not, this is what changed.

### The whole thing, for real

For the times the question is not the contract but whether it works. From the
site's repo:

```bash
npm run dev:stack
```

Brings up the database, the backend and this frontend, builds the element into
`public/`, mints a claim link and starts the site against all three — then
prints a URL to open. The site's `scripts/dev-stack.mjs` drives it; everything is
real, including the model, so a question there costs an API call and one of
the link's allowance.

It overlays `docker-compose.embed.yaml` onto the stack, which widens the
backend's dev CORS list to the site's port. That is a compose `environment`
entry rather than an edit to `backend/.env`: it beats the env file, nothing on
disk changes, and leaving the overlay off puts the list back.

For an inner loop, leave it running and use `npm run watch:embed` here — the
element rebuilds on every change, components included, and the site picks it
up on reload.

### In CI

`npm run test:contract` is what a job would run, after `npm run build:embed`
and a checkout of the site beside this repo. It is not wired up: the site is a
separate repository, so the job needs credentials to check it out, and a token
is not something to add on somebody's behalf.

## Deploying

- **Cache** `/embed.js` short and revalidated — `Cache-Control: public,
  max-age=60, must-revalidate`. It is the entry point; cache it for a year and
  a release reaches nobody. Everything is bundled into this one file, so there
  are no chunk paths to keep stable.
- **CORS on `/embed.js` itself**, not only on the API: it is loaded as a
  module script from another origin, and a module script without
  `Access-Control-Allow-Origin` is blocked before it runs. The failure is
  silent in the network panel's usual reading — the file downloads, the
  element never registers.
- **CORS on the API**: embedded on mringdal.com, the backend calls are
  cross-origin.
  Allow that origin with credentials, and keep the session cookie `SameSite=Lax`
  — same site, different subdomain, so it still travels.
- **Test** what the host actually gets: a Playwright test that loads a page
  with the script tag and the element, and asserts a reply arrives and the
  usage event fires. The standalone suite will not catch a break in the
  element.

## What it does not touch

The element passes `ownsViewport={false}`, so the chat leaves the host page's
`<html>` alone. Standalone, `useViewportHeight` measures the visual viewport
and writes `--app-height` there, which is what keeps the composer above an iOS
keyboard. Embedded there is nothing to write it for — the rule that reads it
is `html { height: var(--app-height) }`, and a shadow tree has no `html` — and
the keyboard is the host's layout problem. The element adopts one stylesheet
into its own shadow root and otherwise leaves the document as it found it.

## Known gaps

- No `greeting` attribute. Overriding the opening message means changing
  `lib/greeting.ts` and `useTranscript`, which decide what it says from the
  session status — not something the element can pass through.
