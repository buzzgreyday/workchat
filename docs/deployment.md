# Deployment

Production is served at **https://chat.mringdal.com** by Caddy (auto Let's Encrypt),
which sits in front of the Next.js frontend and the FastAPI backend.

## TODO before first deploy

- [ ] **DNS** — add an `A` (and ideally `AAAA`) record for `chat.mringdal.com`
  pointing at the production host.
- [ ] **Firewall** — open TCP **80** and TCP/UDP **443** on the host (Caddy
  needs 80 for the HTTP-01 challenge and 443 for HTTPS/HTTP-3).
- [ ] **Secrets** — on the server:
  ```bash
  cp backend/.env.production.example backend/.env
  # Generate each secret with:
  openssl rand -hex 32
  # Fill in JWT_SECRET, TOKEN_HASHING_SECRET, ADMIN_KEY, POSTGRES_PASSWORD,
  # and your real OPENAI_API_KEY. Leave BASE_URL and ALLOWED_HOSTS as
  # https://chat.mringdal.com.

  # Compose only reads env_file for the *containers*; it separately needs a
  # .env next to the compose file to fill in ${POSTGRES_USER} etc. in the
  # compose file itself. Symlink it once so every command below just works.
  ln -s backend/.env .env
  ```
- [ ] **Private CV content** — these files are gitignored (they contain
  personal data) and must be provided on the server:
  - `backend/resources/contact.md` — copy from `contact.md.example` and fill in.
  - `backend/resources/system-prompt.md` — copy from `system-prompt.md.example`.
  - `backend/resources` is bind-mounted into the backend container (not
    baked into the image), so the container's `appuser` (UID/GID 1000)
    needs write access on the host directory:
    ```bash
    sudo chown -R 1000:1000 backend/resources
    ```
- [ ] **Build the index** — after the resource files are in place:
  ```bash
  docker compose -f docker-compose.prod.yaml run --rm backend python -m app.build_index
  ```
  This generates `backend/resources/index.json` (also gitignored) from the
  markdown files. The backend refuses to start without it.
- [ ] **Bring the stack up**:
  ```bash
  docker compose -f docker-compose.prod.yaml up -d --build
  ```
  First run also builds `caddy/` from source (adds the rate-limit module
  via `xcaddy`), which pulls a fair amount of Go modules — expect this
  step to take a few minutes longer than the other services.
- [ ] **Verify**:
  ```bash
  curl -I https://chat.mringdal.com
  curl    https://chat.mringdal.com/api/health
  ```
- [ ] **Mint your first access token** — see "Issue an access token" below.
- [ ] *(Optional)* Set up a nightly `pg_dump` cron — see "Backups" below.

```
Internet ──▶ Caddy (443/80) ──┬─▶ frontend:3000 (Next.js)
                              └─▶ backend:8000  (FastAPI, /api/*)
                                    │
                                    └─▶ db:5432 (Postgres)
```

## Prerequisites

- A host with Docker + Docker Compose and public IPv4/IPv6.
- DNS: an `A`/`AAAA` record for `chat.mringdal.com` pointing to the host.
- Ports **80** and **443** open on the host firewall.

## First-time setup

```bash
git clone https://github.com/buzzgreyday/workchat.git && cd workchat

# Fill in real secrets — see file header for how to generate them.
cp backend/.env.production.example backend/.env
$EDITOR backend/.env

# Compose needs this next to the compose file too, to interpolate
# ${POSTGRES_USER} etc. in docker-compose.prod.yaml itself. Without it every
# compose command fails with "required variable POSTGRES_DB is missing a
# value" unless you pass --env-file backend/.env by hand.
ln -s backend/.env .env

# Provide the CV content files (system-prompt.md, bio.md, etc.).
$EDITOR backend/resources/system-prompt.md

# Build and start.
docker compose -f docker-compose.prod.yaml up -d --build
```

Caddy will provision a Let's Encrypt certificate on first request to
`chat.mringdal.com`. It stores certs in the `caddy_data` volume so restarts
don't re-issue.

## Verify

```bash
docker compose -f docker-compose.prod.yaml ps
curl -I https://chat.mringdal.com
curl    https://chat.mringdal.com/api/health
```

## Update to a new release

```bash
git pull
docker compose -f docker-compose.prod.yaml up -d --build
```

Alembic migrations run automatically in the backend entrypoint before the
server starts.

## Issue an access token

```bash
docker compose -f docker-compose.prod.yaml exec backend \
  curl -s -X POST http://localhost:8000/admin/issue-token \
    -H "X-Admin-Key: $ADMIN_KEY" \
    -H "Content-Type: application/json" \
    -d '{"subject":"jane","job_title":"CTO","company":"Acme","email":"jane@acme.com","phone":"","expires_in_seconds":604800,"max_queries":50,"type":"token"}'
```

## Logs

```bash
docker compose -f docker-compose.prod.yaml logs -f caddy
docker compose -f docker-compose.prod.yaml logs -f backend
docker compose -f docker-compose.prod.yaml logs -f frontend
```

## Backups

The Postgres data lives in the `postgres_data` volume. A minimal dump:

```bash
docker compose -f docker-compose.prod.yaml exec db \
  pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB" > backup-$(date +%F).sql
```

## Notes

- `NEXT_PUBLIC_API_URL` is baked into the frontend at build time as `/api`
  so the browser hits the same origin (no CORS surface for normal traffic).
- `/docs`, `/redoc`, `/openapi.json` are disabled when `DEV_MODE=0`.
- The backend and Postgres are not exposed on the host — only Caddy is.