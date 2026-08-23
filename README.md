# Chat Application

A modern full-stack AI-powered chat application built with **FastAPI**, **Next.js**, **PostgreSQL**, and **Docker**.

The project consists of a Python backend exposing REST APIs and AI integrations, and a React frontend built with Next.js. The application is fully containerized using Docker Compose, making it easy to develop, test, and deploy consistently across environments.

---

# Features

* FastAPI backend
* Next.js frontend
* PostgreSQL database
* SQLAlchemy Async ORM
* Alembic database migrations
* JWT-based authentication
* OpenAI integration
* Dockerized development environment
* TypeScript frontend
* Tailwind CSS UI
* TanStack Query for API communication

---

# Technology Stack

## Backend

* Python 3.13
* FastAPI
* SQLAlchemy 2.x (Async)
* Alembic
* PostgreSQL
* psycopg 3 (binary) — the driver, via `postgresql+psycopg://`
* OpenAI SDK
* uv package manager

## Frontend

* Next.js 16
* React 19
* TypeScript
* Tailwind CSS 4
* TanStack Query
* shadcn/ui
* React Markdown
* JWT Decode

## Infrastructure

* Docker
* Docker Compose

---

# Project Structure

```text
.
├── backend
│   ├── alembic
│   ├── alembic.ini
│   ├── app
│   ├── Dockerfile
│   ├── entrypoint.sh
│   ├── __init__.py
│   ├── pyproject.toml
│   ├── README.md
│   ├── resources             # CV markdown; system-prompt.md + contact.md gitignored
│   └── uv.lock
├── caddy
│   └── Dockerfile            # Caddy + rate-limit module, built via xcaddy
├── Caddyfile                 # prod only; site address comes from $SITE_DOMAIN
├── docker-compose.yaml       # dev
├── docker-compose.prod.yaml  # production (Caddy + services)
├── docs
│   ├── architecture.md
│   ├── database.md
│   ├── deployment.md
│   └── development.md
├── frontend
│   ├── components.json
│   ├── Dockerfile
│   ├── eslint.config.mjs
│   ├── next.config.ts
│   ├── package.json
│   ├── package-lock.json
│   ├── postcss.config.mjs
│   ├── public
│   ├── README.md
│   ├── src
│   └── tsconfig.json
├── CHANGES.md
└── README.md
```

---

# Architecture

```
                    ┌─────────────────────┐
                    │      Browser        │
                    └──────────┬──────────┘
                               │  HTTPS
                               ▼
                          Caddy (TLS)
                               │
                ┌──────────────┴──────────────┐
                │                             │
                ▼                             ▼
         Next.js Frontend             FastAPI Backend (/api/*)
                                              │
                                ┌─────────────┴─────────────┐
                                ▼                           ▼
                           PostgreSQL                   OpenAI API
```

---

# Prerequisites

Before running the project, install:

* Docker
* Docker Compose
* Git

For local Python development outside Docker:

* Python 3.13
* uv

---

# Running the Application

Clone the repository:

```bash
git clone https://github.com/buzzgreyday/workchat.git
cd workchat
```

Create the environment file. Both compose files read `backend/.env` **and**
interpolate `${POSTGRES_USER}` and friends from a `.env` beside the compose
file, so the symlink is required in development too — without it every
`docker compose` command aborts before starting anything:

```bash
cp backend/.env.example backend/.env
ln -s backend/.env .env
```

Add your `OPENAI_API_KEY` to `backend/.env`, then create the system prompt —
the backend raises at import if it is missing or empty:

```bash
cp backend/resources/system-prompt.md.example backend/resources/system-prompt.md
```

Build the containers:

```bash
docker compose build
```

Start all services:

```bash
docker compose up -d
```

Verify that everything is running:

```bash
docker compose ps
```

View backend logs:

```bash
docker compose logs -f backend
```

View frontend logs:

```bash
docker compose logs -f frontend
```

Stop all services:

```bash
docker compose down
```

---

# Build new skills

```bash
cd backend && uv run --env-file .env -m app.build_index
```

---

# Environment Variables

The application uses environment variables for configuration. Secrets are never
committed — `.env` files are gitignored, and only `.env.example` files are tracked.

In production the only real env file is `backend/.env`, read by three different
consumers:

| Consumer | How it reads the file |
| --- | --- |
| Backend outside Docker (local dev) | `load_dotenv(BACKEND_DIR / ".env")` in `app/common/config.py` |
| The `backend` and `db` containers | `env_file: ./backend/.env` in both compose files |
| Compose itself, for `${POSTGRES_USER}` etc. in `docker-compose.prod.yaml` | only ever reads a `.env` sitting next to the compose file |

The third consumer is why a repo-root `.env` also has to exist. Rather than
duplicating the values, symlink it so there is a single source of truth:

```bash
ln -s backend/.env .env
```

Without that symlink every `docker compose` command fails with
`required variable POSTGRES_DB is missing a value`, unless you pass
`--env-file backend/.env` by hand each time.

To set up a new deployment, copy `backend/.env.production.example` to
`backend/.env`, fill in real secrets, then create the symlink.

The frontend needs no env file of its own: the only variable it reads is
`NEXT_PUBLIC_API_URL`, supplied by `environment:` in `docker-compose.yaml` for
dev and baked in as a build arg in `docker-compose.prod.yaml` for production.

---

# Backend

The backend is built with FastAPI and uses SQLAlchemy's asynchronous ORM together with PostgreSQL.

The Docker image:

* Uses Python 3.13 Slim
* Installs dependencies with uv
* Creates an isolated virtual environment
* Runs as a non-root user

Start only the backend:

```bash
docker compose up backend
```

Open a shell:

```bash
docker compose exec backend bash
```

---

# Frontend

The frontend is built with Next.js 16 and React 19.

The Docker image:

* Uses Node.js Alpine
* Installs dependencies
* Builds the production bundle
* Starts the Next.js server
* Exposes port 3000

Start only the frontend:

```bash
docker compose up frontend
```

Open a shell:

```bash
docker compose exec frontend sh
```

---

# Database

The project uses PostgreSQL with Alembic for schema migrations.

## Generate a Migration

Whenever SQLAlchemy models change. **Not** on a new deployment — the migrations
are committed and `backend/entrypoint.sh` already runs `alembic upgrade head` at
startup, so a fresh deploy needs nothing here:

```bash
docker compose exec backend alembic revision --autogenerate -m "migration description"
```

Example:

```bash
docker compose exec backend alembic revision --autogenerate -m "add users and tokens"
```

Always review generated migrations before applying them.

---

## Apply Migrations

Migrations will be performed automatically when docker backend container is started, to set latest.

```bash
docker compose exec backend alembic upgrade head
```

---

## Show Current Migration

```bash
docker compose exec backend alembic current
```

---

## Migration History

```bash
docker compose exec backend alembic history
```

---

## Connect to PostgreSQL

Executed command in the "db" docker container.

-U for username, e.g. "postgres"

-d for database schema, e.g. "db"

```bash
docker compose exec db psql -U postgres -d db
```

List tables:

```sql
\dt
```

Exit PostgreSQL:

```sql
\q
```

---

# API Documentation

Once the backend is running:

Swagger UI:

```
http://localhost:8000/docs
```

Redoc UI:

```
http://localhost:8000/redoc
```

OpenAPI Specification:

```
http://localhost:8000/openapi.json
```

---

# Docker Commands

Build containers:

```bash
docker compose build
```

Rebuild backend:

```bash
docker compose build --no-cache backend
```

Restart backend:

```bash
docker compose restart backend
```

Restart frontend:

```bash
docker compose restart frontend
```

Restart all services:

```bash
docker compose restart
```

Stop services:

```bash
docker compose stop
```

Remove containers and volumes:

```bash
docker compose down -v
```

View logs:

```bash
docker compose logs -f
```

---

# Development Workflow

Typical development workflow:

1. Update application code. Both trees are bind-mounted and both live-reload —
   the frontend via `npm run dev`, the backend via `uvicorn --reload` (dev
   compose only). No rebuild is needed for source edits. The backend watcher is
   scoped to `backend/app/`, so changes under `backend/alembic/` need a
   `docker compose restart backend`.
2. If SQLAlchemy models changed:
   1. Generate a migration — `docker compose exec backend alembic revision
      --autogenerate -m "…"`.
   2. Review it. Autogenerate misses things like server defaults and renames.
   3. Apply it — `docker compose exec backend alembic upgrade head`.
3. If you edited anything in `backend/resources/`, rebuild the search index, or
   `/chat` will keep answering from the old one:
   `docker compose run --rm backend python -m app.build_index`
4. Run the tests on the host — `cd backend && uv run pytest` (see [Testing](#testing)).
5. Rebuild only when dependencies change — `docker compose build backend`
   after `pyproject.toml`/`uv.lock`, or `frontend` after `package.json`.
6. Commit code and migration files together, so a checkout never has models and
   schema out of step.

---

# Testing

Run on the host, not in the container — the image is built with
`uv sync --frozen --no-dev` and `pytest` is in the `dev` dependency group, so it
is not installed inside either the dev or prod image:

```bash
cd backend && uv sync && uv run pytest
```

Lint the frontend:

```bash
docker compose exec frontend npm run lint
```

---

# Troubleshooting

## Backend fails to start

```bash
docker compose logs backend
```

The two most common causes are configuration, not code:

- **`system prompt not found` / `is empty`** — `backend/resources/system-prompt.md`
  is gitignored and read at import, so the process exits before serving.
  `cp backend/resources/system-prompt.md.example backend/resources/system-prompt.md`
- **`<VAR> not found or empty in environment variables`** — `backend/.env` is
  missing a required key. Compare it against `backend/.env.example`.

If `docker compose` itself aborts with `required variable POSTGRES_DB is
missing a value` before any container starts, the root `.env` symlink is
missing: `ln -s backend/.env .env`.

---

## Database connection issues

Verify the database container is running:

```bash
docker compose ps
```

---

## Migration issues

Verify the current migration:

```bash
docker compose exec backend alembic current
```

Apply pending migrations:

```bash
docker compose exec backend alembic upgrade head
```

---

## Rebuild after dependency changes

Backend:

```bash
docker compose build --no-cache backend
```

Frontend:

```bash
docker compose build --no-cache frontend
```

---

# Production Deployment

Caddy handles TLS via Let's Encrypt and proxies `/api/*` to the backend,
everything else to the Next.js frontend. Alembic migrations run automatically
in the backend entrypoint, so a fresh database needs no manual step.

**→ [`docs/deployment.md`](docs/deployment.md)** is the single source of truth
for deploying: prerequisites, the ordered first-deployment checklist, issuing
access tokens, logs and backups.

---

# Future Improvements

Possible future enhancements include:

* AuthHandler
* Refresh token (via claim/invite id/token)
* Token persistence
* Handle max queries reached, invalid/expired token, etc. in frontend

* ChatClient
* Abstractions

* Move the hardcoded conditional prompts from the code to separate files
* Resource search scoring
* CI/CD pipeline
* Automated testing
* Background workers
* Monitoring and metrics
* Centralized logging
* Backup automation
* API versioning
* Chat client polymorph and factory (YAGNI)

