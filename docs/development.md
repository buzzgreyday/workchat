# Development

## First run

`docker compose up -d` on a fresh clone fails: both compose files read
`backend/.env` for the containers *and* interpolate `${POSTGRES_USER}` and
friends from a `.env` beside the compose file. Neither exists until you create
them.

```bash
cp backend/.env.example backend/.env
ln -s backend/.env .env

# Add your OPENAI_API_KEY to backend/.env, then provide the system prompt --
# app/common/config.py reads it at import and raises if missing or empty.
cp backend/resources/system-prompt.md.example backend/resources/system-prompt.md

docker compose up -d
```

The dev stack exposes the backend on `:8000` and the frontend on `:3000`
directly; Caddy is production-only.

`/chat` and `/chat/stream` additionally needs the search index, which is generated from the
markdown in `backend/resources/`:

```bash
docker compose run --rm backend python -m app.build_index
```

Re-run that whenever you add or edit a file there.

## Branches

Three tiers, and code moves one way through them:

```
experimental/*  ──PR──>  development  ──PR──>  main
    CI (fast)              CI (full)          CI (full) + deploy
```

| Branch | Purpose | What runs |
|---|---|---|
| `main` | Production. Its HEAD is what is on the server. | Full CI, then a deploy that waits for approval, then a release tag if the version bumped |
| `development` | Integration. Everything lands here first and is judged here. | Full CI |
| `experimental/*` | Anything in progress — a feature, a spike, a refactor. | Backend, frontend and the secret scan on each push |

**`main` accepts merges from `development` and nothing else.** Branch protection
can require a pull request and a green build, but it cannot say where the pull
request came from, so the `Branch policy` job in CI fails any PR into `main`
whose head is not `development`.

### Why experimental/* gets less

Pushes to `experimental/*` skip the migration, Caddy and image-build jobs. They
are the slow ones and they rarely catch anything mid-spike; skipping them keeps
a push under a minute. Nothing is lost, because they run again on the PR into
`development` — the branch is short-lived, the gate is at the merge, and the
promotion PR into `main` runs them a second time.

The secret scan is never skipped. A key pushed to a public repo is compromised
the moment it lands, whatever branch it landed on.

### Promoting to production

```bash
git switch development && git pull
# ... merge your experimental/* PRs here, let CI go green ...
gh pr create --base main --head development --title "Release: <what changed>"
```

Bump the version in `backend/pyproject.toml` on `development` before the
promotion PR if this release should be tagged — the release job reads it and
does nothing when it has not changed. See [deployment](deployment.md).

## Tests

Tests are not available inside the containers — the image is built with
`uv sync --frozen --no-dev`, and `pytest` lives in the `dev` dependency group.
Run them on the host:

```bash
cd backend && uv sync && uv run pytest
```

Type checking runs the same way, and is not part of the test run, so running it
locally is a deliberate act. CI runs it on every push regardless:

```bash
cd backend && uv run mypy
```

The frontend is checked by `npx tsc --noEmit` and linted by `npx eslint`, both
from `frontend/`. `next build` runs the type check itself, so a green build
implies a green `tsc`.

## API docs

`/docs`, `/redoc` and `/openapi.json` are served only while `DEV_MODE=1`. They
are disabled in production.