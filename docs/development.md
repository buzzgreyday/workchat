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

## Tests

Tests are not available inside the containers — the image is built with
`uv sync --frozen --no-dev`, and `pytest` lives in the `dev` dependency group.
Run them on the host:

```bash
cd backend && uv sync && uv run pytest
```

## API docs

`/docs`, `/redoc` and `/openapi.json` are served only while `DEV_MODE=1`. They
are disabled in production.