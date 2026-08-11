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
* asyncpg
* psycopg (binary)
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
│   ├── alembic
│   ├── alembic.ini
│   ├── app
│   ├── Dockerfile
│   ├── entrypoint.sh
│   ├── __init__.py
│   ├── pyproject.toml
│   ├── README.md
│   ├── resources
│   └── uv.lock
├── Caddyfile
├── docker-compose.yaml           # dev
├── docker-compose.prod.yaml      # production (Caddy + services)
├── docs
│   ├── architecture.md
│   ├── database.md
│   ├── deployment.md
│   └── development.md
├── frontend
│   ├── components.json
│   ├── Dockerfile
│   ├── eslint.config.mjs
│   ├── next.config.ts
│   ├── node_modules
│   ├── package.json
│   ├── package-lock.json
│   ├── postcss.config.mjs
│   ├── public
│   ├── README.md
│   ├── src
│   └── tsconfig.json
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
git clone <repository-url>
cd <repository-name>
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

The application uses environment variables for configuration.

Store sensitive values in a local `.env` files on server.

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

Whenever SQLAlchemy models change or new deployment:

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

1. Update application code.
2. Modify SQLAlchemy models if required.
3. Generate an Alembic migration.
4. Review the generated migration.
5. Apply the migration.
6. Test the application.
7. Commit both code and migration files.

---

# Testing

When a test suite is available:

```bash
docker compose exec backend pytest
```

Lint the frontend:

```bash
docker compose exec frontend npm run lint
```

---

# Troubleshooting

## Backend fails to start

Check the backend logs:

```bash
docker compose logs backend
```

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

See [`docs/deployment.md`](docs/deployment.md) for the full guide to running
this on `chat.mringdal.com`.

Short version:

```bash
cp backend/.env.production.example backend/.env   # fill in real secrets
docker compose -f docker-compose.prod.yaml up -d --build
```

Caddy handles TLS via Let's Encrypt and proxies `/api/*` to the backend,
everything else to the Next.js frontend. Alembic migrations run automatically
in the backend entrypoint.

---

# Future Improvements

Possible future enhancements include:

* Keep chat history in database (server-side)
* First request either takes history or the system-prompt (system-prompt should be added server-side only). Also, server-side history in Postgres only.
* Handle max_queries, invalid token, etc. in frontend
* Token persistence
* CI/CD pipeline
* Automated testing
* Redis caching
* Background workers
* Rate limiting
* Monitoring and metrics
* Centralized logging
* Backup automation
* Multi-environment configuration
* API versioning
* Chat client polymorph and factory (YAGNI)

