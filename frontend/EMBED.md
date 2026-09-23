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
| `owner-github` | GitHub URL for the header. Set it empty for no link. |
| `owner-linkedin` | LinkedIn URL for the header. Set it empty for no link. |

The app reads the owner from the environment during its server render. An
embed has no server render, so the host page says who this is — or says
nothing and gets the defaults. Absent and empty are different answers: an
absent `owner-linkedin` takes the default, an empty one means "no LinkedIn"
and the header shows no link rather than somebody else's.

`about` seeds the composer rather than asking: the visitor reads it, edits it
or deletes it, and a handful of questions is too few to spend one on wording
nobody saw. It is read on the element's first render, so set it in the markup
or before the element is inserted — React does the latter by itself. Changing
it later does not re-seed, which is what stops it overwriting what somebody is
halfway through typing.

**Events** (bubbling and composed, so listen on the element)

| Event | Detail |
| --- | --- |
| `workchat-usage` | `{ used, remaining, max }` |

There is no close event. Running in the host's document, Escape reaches their
`<dialog>` on its own — forwarding it was something only a frame needed.

**CSS variables** — the palette is the `--chat-*` set declared at the top of
`src/app/globals.css`: `--chat-bg`, `--chat-panel`, `--chat-line`, and the
rest. Set them on the element itself:

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

The element fills its container and sets no height of its own beyond `100%`.
Give the container one, or give the element one, or it collapses.

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
