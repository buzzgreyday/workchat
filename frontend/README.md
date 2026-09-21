# Frontend

The chat page a hiring manager lands on. Next.js App Router, one route, talking
to the FastAPI backend in `../backend`.

`src/hooks/useSession.ts` owns the access token and how it is renewed.
Everything else is split by what it knows:

| where | what it knows |
|---|---|
| `src/lib/copy.ts` | every string the app says to a person, and nothing else |
| `src/lib/failure.ts` | which failure deserves which of those strings |
| `src/lib/greeting.ts` | what the greeting says, given a session status |
| `src/lib/transcript.ts` | the transcript reducer — what may happen to a message |
| `src/hooks/useChat.ts` | orchestration of one turn, and only that |
| `src/hooks/use{Transcript,Usage,ConversationMemory}.ts` | one concern each |
| `src/components/chat/ChatProvider.tsx` | two contexts, so a streamed token re-renders the transcript and not the composer |
| `src/app/globals.css` | **the whole visual scheme** — colour, type, spacing, radius. To restyle the app, you should not need to read past `@layer base` |

The first four are pure — no React, no fetch — which is what makes them
readable without a renderer in your head. The components under
`src/components/chat/` read what they need from the provider rather than being
handed it.

## Running it

The usual way is the whole stack from the repository root — `docker compose up`
— which gives you a backend to talk to. See [`../docs/development.md`](../docs/development.md).

On its own:

```bash
npm install
npm run dev          # http://localhost:3000
```

You will need `NEXT_PUBLIC_API_URL` pointing at a backend, and a link with a
`?claim=` on it; without a credential the page says so rather than showing a
chat box.

`?token=` — the v1 shape, where the link carries the access token itself — is
still accepted, because those links are in inboxes and cannot be reissued. It
is on its way out: a URL is copied into browser histories, sent as a referrer
and written to every proxy log on the way, which is not where a credential
belongs. `e2e/legacy.spec.ts` is the only place the suite still drives it, and
should be deleted when the last of those links expires.

## Tests

```bash
npm run test:e2e             # everything
npx playwright test --ui     # pick through them interactively
```

Playwright, against the standalone production build — the same server
`Dockerfile` runs, because some of what is asserted is how that server reads its
environment. The config builds and starts it for you.

**The backend is mocked at the network boundary** (`e2e/backend.ts`), which is
the point rather than a shortcut. These tests are about frontend behaviour no
type checker can see — a composer left dead after a failed reply, a transcript
that does or does not survive a reload — and producing those states for real
would need a database, an OpenAI key and a way to make a model fail on command.
The backend's own contract is covered by its pytest suite.

What they cover, and why each one exists:

| file | what broke, or could |
|---|---|
| `chat.spec.ts` | a failed reply left the composer disabled with nothing on screen saying why |
| `reload.spec.ts` | F5 kept the session but lost the conversation, and split the transcript in two |
| `greeting.spec.ts` | "Hi! 👋" addressed to nobody while a claim link was being exchanged |
| `owner.spec.ts` | the header named the author, and could only be changed by rebuilding the image |
| `mobile.spec.ts` | a white band under the chat on a phone, and a composer that scrolled before anything was typed |
| `session.spec.ts` | four of `useSession`'s five statuses had no test at all — a spent link, a broken one, no link, and a token that expires mid-visit |
| `viewport.spec.ts` | `dvh` is the layout viewport, which iOS does not shrink for the keyboard |
| `theme.spec.ts` | the background colour exists twice, once as CSS and once as a `<meta>` literal |
| `legacy.spec.ts` | the `?token=` links still in inboxes — delete with them |

Browsers are not installed by `npm install`:

```bash
npx playwright install chromium
```

Only chromium. These are behaviour tests, not a compatibility matrix — the
`mobile` project is a Pixel 5 *viewport*, which is a chromium device
descriptor, so it needs no second browser. `mobile.spec.ts` makes claims that
are only true at phone width and is skipped on the desktop project; everything
else runs on both.

## Configuration

`NEXT_PUBLIC_API_URL` is baked in at build time, so it belongs to the image.
`OWNER_NAME`, `OWNER_GITHUB_URL` and `OWNER_LINKEDIN_URL` are read on the server
per request, so changing one is a restart — see
[`../docs/deployment.md`](../docs/deployment.md). An owner variable that is set
but empty means "there isn't one" and hides the link; unset means "use the
default".
