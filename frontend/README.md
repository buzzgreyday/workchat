# Frontend

The chat page a hiring manager lands on. Next.js App Router, one route, talking
to the FastAPI backend in `../backend`.

Most of the app is `src/hooks/useSession.ts`, which owns the access token and
how it is renewed, and `src/hooks/useChat.ts`, which owns the transcript. The
components under `src/components/chat/` render what those two decide.

## Running it

The usual way is the whole stack from the repository root — `docker compose up`
— which gives you a backend to talk to. See [`../docs/development.md`](../docs/development.md).

On its own:

```bash
npm install
npm run dev          # http://localhost:3000
```

You will need `NEXT_PUBLIC_API_URL` pointing at a backend, and a link with a
`?token=` or `?claim=` on it; without a credential the page says so rather than
showing a chat box.

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

Browsers are not installed by `npm install`:

```bash
npx playwright install chromium
```

Only chromium. These are behaviour tests, not a compatibility matrix.

## Configuration

`NEXT_PUBLIC_API_URL` is baked in at build time, so it belongs to the image.
`OWNER_NAME`, `OWNER_GITHUB_URL` and `OWNER_LINKEDIN_URL` are read on the server
per request, so changing one is a restart — see
[`../docs/deployment.md`](../docs/deployment.md). An owner variable that is set
but empty means "there isn't one" and hides the link; unset means "use the
default".
