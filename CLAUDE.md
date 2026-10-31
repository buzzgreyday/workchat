# Working on workchat

The docs are the architecture — read the one that covers the change before
making it. This file is the rules for working here, not a second description
of the code.

| Doc | Covers |
|---|---|
| `docs/architecture.md` | request path, auth as a dependency, the chat turn as generators, the CV index |
| `docs/database.md` | schema and migrations |
| `docs/design.md` | the look: tokens, type, what each colour is for |
| `docs/privacy.md` | what is stored, for how long, and what purges it |
| `docs/deployment.md` | the server, CI/CD, other sites on the host, backups |
| `docs/development.md` | first run, branches, tests |
| `frontend/EMBED.md` | the `<workchat-chat>` element — a public contract (below) |

The frontend is Next.js 16 and differs from what you know: read
`frontend/AGENTS.md` and the guide in `frontend/node_modules/next/dist/docs/`
before writing frontend code.

Many decisions are recorded in module docstrings rather than the docs —
`app/services/auth.py` is the example. Read the docstring before changing a
module whose shape looks odd; it is usually odd on purpose.

## Git

- Work on a `feat/*`, `fix/*` or `chore/*` branch cut from `development`.
  Commit there.
- **Do not merge, push to `development` or `main`, tag, or cut a release.** The
  owner does those. `main` takes pull requests from `development` only (CI
  enforces it), and a green `main` queues a production deploy for approval.
- Commit subjects are conventional, with a scope where one fits —
  `fix(frontend):`, `feat(embed):`, `fix(eval):`, `chore(release):` — followed
  by a plain sentence saying what is now true:
  `fix(frontend): an empty ?claim= does not linger in the address bar`.
- A release, when asked for, is one `chore(release): X.Y.Z` commit: the same
  version in `backend/pyproject.toml` **and** `frontend/package.json`, and a
  section in `CHANGES.md` in its existing voice. The repo is versioned as one
  unit. The deploy tags it once it has reached the server, if the version
  changed.

## Checking a change

Node 22 for the frontend, from `.nvmrc` — run `nvm use` first. The shell's
default Node may be older than Next 16 accepts.

On the host — the images are built without dev dependencies, so neither
`pytest` nor `mypy` exists inside a container:

```bash
cd backend && uv run mypy && uv run pytest -q
cd frontend && npx tsc --noEmit && npx eslint && npx next build
cd frontend && npm run test:contract     # ../website's e2e suite against this bundle
cd frontend && npm run test:e2e
```

After changing a SQLAlchemy model: generate the migration
(`docker compose exec backend alembic revision --autogenerate -m "…"`), read
it — autogenerate misses server defaults and renames — and commit it with the
model. CI fails on drift (`alembic check`).

After changing the tags on anything in `backend/resources/`: regenerate the
skills list (`cd backend && uv run -m app.build_skills`) and commit it. The
search index itself needs nothing; it is rebuilt at startup.

### Evals

`backend/tests/evals/` measures how often the chat wrongly denies something
the CV contains. It drives a **live** backend with the real model, so every run
costs API calls — run it only when asked, or when a change is meant to move the
number. Usage, and how to pin the model being measured, is in the
`run_eval.py` docstring. Results land in `tests/evals/results/`, gitignored.

## Things that are not in the checkout

- `backend/.env`, with a `.env` symlink to it at the root. Without the
  symlink every `docker compose` command aborts.
- `backend/resources/system-prompt.md` and `contact.md` are gitignored. The
  backend refuses to start without the system prompt; copy the `.example`.
- **This repository is public.** Nothing from `.env`, the system prompt,
  `contact.md`, eval transcripts or the database goes into a commit, a PR or
  an issue.

## The embed is a contract

`<workchat-chat>` is loaded at runtime by `../website` (mringdal.com), which has
no build step in common with this repo and cannot pin a version. Its
attributes, its one event and its `--chat-*` variables, as written in
`frontend/EMBED.md`, are a public API:

- Change `EMBED.md` in the same change as the element. `npm run test:contract`
  builds the bundle and runs the website's own tests against it — the only
  check that catches the contract moving. Run it for any change to the element.
- A change to the contract also needs `types/workchat.d.ts` and
  `e2e/fixtures/workchat-chat.js` in `../website` updated — say so, and offer
  to do it there. That repo has its own `CLAUDE.md` and a different branch
  flow (`dev`, and `main` deploys without approval).
- The site runs the element in its own page, not a frame, on a sibling
  subdomain. Cookies (`SameSite=Lax`) and CORS-with-credentials depend on that;
  see the website's README before touching either.

## Writing

The docs and `CHANGES.md` have a voice: short declarative sentences that
explain *why*, not just *what*, and record the alternative that was rejected.
Match it. Update the doc that describes a behaviour in the same change that
alters it.
