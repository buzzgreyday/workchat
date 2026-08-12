# Deployment

The stack is served by Caddy (automatic Let's Encrypt certificates) in front of
the Next.js frontend and the FastAPI backend. Nothing is tied to a particular
domain — you set yours in `backend/.env`.

The author's instance runs at https://chat.mringdal.com; every command below
uses your own `SITE_DOMAIN` instead.

## TODO before first deploy

- [ ] **DNS** — add an `A` (and ideally `AAAA`) record for the hostname you
  intend to use, pointing at the production host. Caddy cannot obtain a
  certificate until this resolves.
- [ ] **Firewall** — open TCP **80** and TCP/UDP **443** on the host (Caddy
  needs 80 for the HTTP-01 challenge and 443 for HTTPS/HTTP-3).
- [ ] **Secrets** — on the server:
  ```bash
  cp backend/.env.production.example backend/.env
  # Generate each secret with:
  openssl rand -hex 32
  # Fill in JWT_SECRET, TOKEN_HASHING_SECRET, ADMIN_KEY, POSTGRES_PASSWORD
  # and your real OPENAI_API_KEY.

  # Compose only reads env_file for the *containers*; it separately needs a
  # .env next to the compose file to fill in ${POSTGRES_USER} etc. in the
  # compose file itself. Symlink it once so every command below just works.
  ln -s backend/.env .env
  ```
- [ ] **Your domain** — set all four of these in `backend/.env` to the hostname
  you control. They must agree; the Caddyfile and compose file read the first
  two, so there is no tracked file to edit:
  - `SITE_DOMAIN` — the Caddy site address, e.g. `chat.example.com` (no scheme)
  - `ACME_EMAIL` — where Let's Encrypt sends expiry and problem notices
  - `BASE_URL` — e.g. `https://chat.example.com`, used in QR-code token links
  - `ALLOWED_HOSTS` — e.g. `https://chat.example.com`, CORS origins (scheme required)
- [ ] **Content and private files** — `backend/resources/` ships with the
  author's CV. **Replace every `.md` file there with your own content**, or the
  site will answer questions about someone else. Two files are gitignored and
  must be created:
  - `backend/resources/system-prompt.md` — the backend **will not start**
    without this; `config.py` reads it at import and raises if it is missing or
    empty.
    ```bash
    cp backend/resources/system-prompt.md.example backend/resources/system-prompt.md
    ```
  - `backend/resources/contact.md` — copy from `contact.md.example` and fill in.
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
  markdown files. It is read per request rather than at startup, so the backend
  boots and `/health` passes without it — but `/chat` cannot answer until it
  exists.
- [ ] **Bring the stack up**:
  ```bash
  docker compose -f docker-compose.prod.yaml up -d --build
  ```
  First run also builds `caddy/` from source (adds the rate-limit module
  via `xcaddy`), which pulls a fair amount of Go modules — expect this
  step to take a few minutes longer than the other services.
- [ ] **Verify** (substitute your own domain):
  ```bash
  curl -I https://chat.example.com
  curl    https://chat.example.com/api/health
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
- DNS: an `A`/`AAAA` record for your hostname pointing to the host.
- Ports **80** and **443** open on the host firewall.

## First-time setup

The complete sequence. Every step is required — skipping the system prompt or
the symlink stops the stack from starting at all.

```bash
git clone https://github.com/buzzgreyday/workchat.git && cd workchat

# 1. Secrets and your domain. Set SITE_DOMAIN, ACME_EMAIL, BASE_URL and
#    ALLOWED_HOSTS to the hostname you control, plus the generated secrets.
cp backend/.env.production.example backend/.env
$EDITOR backend/.env

# 2. Compose needs .env next to the compose file too, to interpolate
#    ${POSTGRES_USER} etc. in docker-compose.prod.yaml itself. Without it every
#    compose command fails with "required variable POSTGRES_DB is missing a
#    value" unless you pass --env-file backend/.env by hand.
ln -s backend/.env .env

# 3. The system prompt. The backend raises at import without it.
cp backend/resources/system-prompt.md.example backend/resources/system-prompt.md
$EDITOR backend/resources/system-prompt.md

# 4. Your contact details, and your own CV content in place of the author's.
cp backend/resources/contact.md.example backend/resources/contact.md
$EDITOR backend/resources/contact.md
$EDITOR backend/resources/*.md

# 5. The container runs as UID/GID 1000 and writes into this bind mount.
sudo chown -R 1000:1000 backend/resources

# 6. Generate the search index from the markdown files.
docker compose -f docker-compose.prod.yaml run --rm backend python -m app.build_index

# 7. Build and start.
docker compose -f docker-compose.prod.yaml up -d --build
```

Caddy provisions a Let's Encrypt certificate on the first request to your
`SITE_DOMAIN`. Certificates live in the `caddy_data` volume, so restarts do not
re-issue them — which matters, because Let's Encrypt rate-limits duplicate
certificates to 5 per week.

## Verify

```bash
docker compose -f docker-compose.prod.yaml ps
curl -I https://chat.example.com          # your SITE_DOMAIN
curl    https://chat.example.com/api/health
```

## Update to a new release

```bash
git pull
docker compose -f docker-compose.prod.yaml up -d --build
```

Alembic migrations run automatically in the backend entrypoint before the
server starts.

## Issue an access token

Run this from the host, against your public URL. `ADMIN_KEY` is read out of
`backend/.env` rather than assumed to be in your shell:

```bash
curl -s -X POST https://chat.example.com/api/admin/issue-token \
  -H "X-Admin-Key: $(grep '^ADMIN_KEY=' backend/.env | cut -d= -f2-)" \
  -H "Content-Type: application/json" \
  -d '{"subject":"Jane Doe","job_title":"CTO","company":"Acme","email":"jane@acme.com","phone":"","expires_in_seconds":604800,"max_queries":50,"type":"token"}'
```

Not `docker compose exec backend curl …`: the backend image is
`python:3.13-slim` and ships no curl, and `$ADMIN_KEY` in that form would be
expanded by the host shell (where it is unset) rather than inside the
container, sending an empty header and getting a 401.

## Logs

```bash
docker compose -f docker-compose.prod.yaml logs -f caddy
docker compose -f docker-compose.prod.yaml logs -f backend
docker compose -f docker-compose.prod.yaml logs -f frontend
```

## Backups

The Postgres data lives in the `postgres_data` volume. A minimal dump:

The variables must expand *inside* the container, so wrap the command in
`sh -c` with single quotes — otherwise your host shell substitutes them, they
are empty there, and `pg_dump` fails with `role "root" is not permitted to log
in` while leaving a 0-byte file behind:

```bash
docker compose -f docker-compose.prod.yaml exec -T db \
  sh -c 'pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB"' > backup-$(date +%F).sql

# Always check the dump is non-empty before relying on it.
ls -lh backup-*.sql
```

## Notes

- `NEXT_PUBLIC_API_URL` is baked into the frontend at build time as `/api`
  so the browser hits the same origin (no CORS surface for normal traffic).
- `/docs`, `/redoc`, `/openapi.json` are disabled when `DEV_MODE=0`.
- The backend and Postgres are not exposed on the host — only Caddy is.