# Deployment

The stack is served by Caddy (automatic Let's Encrypt certificates) in front of
the Next.js frontend and the FastAPI backend. Nothing is tied to a particular
domain — you set yours in `backend/.env`. The author's instance runs at
https://chat.mringdal.com; every command below uses your own `SITE_DOMAIN`.

```
Internet ──▶ Caddy (443/80) ──┬─▶ frontend:3000 (Next.js)
                              └─▶ backend:8000  (FastAPI, /api/*)
                                    │
                                    └─▶ db:5432 (Postgres)
```

## Prerequisites

- A host with Docker + Docker Compose and public IPv4/IPv6.
- DNS: an `A` (and ideally `AAAA`) record for your hostname, pointing at the
  host. Caddy cannot obtain a certificate until this resolves.
- Ports **80** and **443** open on the host firewall — Caddy needs 80 for the
  HTTP-01 challenge and 443 for HTTPS/HTTP-3.

## First deployment

Every step is required. Skipping the system prompt or the `.env` symlink stops
the stack from starting at all.

```bash
git clone https://github.com/buzzgreyday/workchat.git && cd workchat
```

- [ ] **1. Secrets.** Generate each with `openssl rand -hex 32`, and add your
      real `OPENAI_API_KEY`.
      ```bash
      cp backend/.env.production.example backend/.env
      $EDITOR backend/.env   # JWT_SECRET, TOKEN_HASHING_SECRET, ADMIN_KEY,
                             # POSTGRES_PASSWORD, OPENAI_API_KEY
      ```

- [ ] **2. Your domain.** In the same file, set all four to the hostname you
      control. They must agree. The Caddyfile and compose file read the first
      two, so there is no tracked file to edit:
      - `SITE_DOMAIN` — Caddy site address, e.g. `chat.example.com` (no scheme)
      - `ACME_EMAIL` — where Let's Encrypt sends expiry and problem notices
      - `BASE_URL` — e.g. `https://chat.example.com`, used in QR-code token links
      - `ALLOWED_HOSTS` — e.g. `https://chat.example.com`, CORS origins (scheme required)

- [ ] **3. The `.env` symlink.** Compose reads `env_file` for the *containers*,
      but separately needs a `.env` beside the compose file to interpolate
      `${POSTGRES_USER}` etc. in the compose file itself. Without it every
      compose command fails with `required variable POSTGRES_DB is missing a
      value` unless you pass `--env-file backend/.env` by hand.
      ```bash
      ln -s backend/.env .env
      ```

- [ ] **4. The system prompt.** Gitignored, and the backend **will not start**
      without it — `config.py` reads it at import and raises if it is missing or
      empty.
      ```bash
      cp backend/resources/system-prompt.md.example backend/resources/system-prompt.md
      $EDITOR backend/resources/system-prompt.md
      ```

- [ ] **5. Your content.** `backend/resources/` ships with the author's CV.
      **Replace every `.md` file with your own**, or the site will answer
      questions about someone else. `contact.md` is gitignored and must be
      created.
      ```bash
      cp backend/resources/contact.md.example backend/resources/contact.md
      $EDITOR backend/resources/contact.md
      $EDITOR backend/resources/*.md
      ```

- [ ] **6. Ownership.** `backend/resources` is bind-mounted rather than baked
      into the image, and the container runs as UID/GID 1000, which needs write
      access to it.
      ```bash
      sudo chown -R 1000:1000 backend/resources
      ```

- [ ] **7. Build the index.** Generates `backend/resources/index.json`
      (gitignored) from the markdown. It is read per request rather than at
      startup, so the backend boots and `/health` passes without it — but
      `/chat` cannot answer until it exists.
      ```bash
      docker compose -f docker-compose.prod.yaml run --rm backend python -m app.build_index
      ```

- [ ] **8. Bring the stack up.** The first run also builds `caddy/` from source
      (adding the rate-limit module via `xcaddy`), which pulls a fair amount of
      Go modules — expect this to take a few minutes longer than the rest.
      ```bash
      docker compose -f docker-compose.prod.yaml up -d --build
      ```

- [ ] **9. Verify** — see below.
- [ ] **10. Mint your first access token** — see "Issue an access token".
- [ ] *(Optional)* Set up a nightly `pg_dump` cron — see "Backups".

Caddy provisions a Let's Encrypt certificate on the first request to your
`SITE_DOMAIN`. Certificates live in the `caddy_data` volume, so restarts do not
re-issue them — which matters, because Let's Encrypt rate-limits duplicate
certificates to 5 per week.

Alembic migrations run automatically in the backend entrypoint, so a fresh
database is created and brought to head with no manual step.

## Verify

```bash
docker compose -f docker-compose.prod.yaml ps
curl -I https://chat.example.com          # your SITE_DOMAIN
curl    https://chat.example.com/api/health
```

## Update to a new release

```bash
git pull
sudo chown -R 1000:1000 backend/resources
docker compose -f docker-compose.prod.yaml up -d --build
docker compose -f docker-compose.prod.yaml run --rm backend python -m app.build_index
```

The order matters, and none of the four steps is optional:

- **The ownership step is not a one-off from first deployment.** `git pull`
  writes the files it updates as whichever user runs it, and the container needs
  `backend/resources` owned by UID/GID 1000 (see step 6). Otherwise
  `build_index` fails part-way with a permission error on `skills.md`, after it
  has already rewritten `index.json` — leaving a fresh index beside a stale
  skills list.
- **Rebuild the image before building the index.** Only `backend/resources` is
  bind-mounted; the application code, `build_index.py` included, is baked into
  the image. Running the index build first would run the *previous* release's
  indexer over the new content.
- **`build_index` does not run itself.** `index.json` is gitignored and read per
  request, so a release that changes any CV record leaves the site answering
  from the old index until this runs — `/health` keeps passing throughout, so
  nothing surfaces the staleness for you.

Afterwards `git status` should be clean. `skills.md` is tracked but rewritten by
`build_index`; since ranking ties break on the tag name, regenerating it on the
server reproduces the committed file byte for byte. If it shows as modified, the
committed copy was generated from different content — regenerate it locally and
commit that, rather than leaving the working tree dirty for the next `git pull`
to collide with.

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

## Read what hirers asked

Chat turns are stored in Postgres and read through the admin API, using the same
`ADMIN_KEY` as token issuance:

```bash
KEY=$(grep '^ADMIN_KEY=' backend/.env | cut -d= -f2-)

# Recent conversations, newest activity first
curl -s https://chat.example.com/api/admin/conversations -H "X-Admin-Key: $KEY"

# One conversation in full
curl -s https://chat.example.com/api/admin/conversations/<id> -H "X-Admin-Key: $KEY"

# Erase one conversation's content, keeping counts and timings
curl -s -X POST https://chat.example.com/api/admin/conversations/<id>/redact \
  -H "X-Admin-Key: $KEY"
```

`/admin/conversations` accepts `limit` (1-200, default 50), `offset`, `company`
and `since`.

These return hiring managers' questions verbatim, protected by one static header
secret. Caddy rate-limits `/api/admin*` to 5 requests per minute per IP, but if
you want defence in depth, restricting `/api/admin*` to a known source address at
the Caddy layer is the obvious next step — deliberately not configured here,
since a wrong address locks you out of minting tokens.

**Content is scrubbed after 30 days.** Add the purge to the same crontab as the
backup:

```
30 3 * * * /usr/bin/flock -n /tmp/workchat-purge.lock /root/ai-cv/scripts/purge-chat-content.sh >> /var/log/workchat/purge.log 2>&1
```

Override the window with `CHAT_RETENTION_DAYS` in `backend/.env`. See
`docs/database.md` for the erasure order and the backup caveat.

## Logs

```bash
docker compose -f docker-compose.prod.yaml logs -f caddy
docker compose -f docker-compose.prod.yaml logs -f backend
docker compose -f docker-compose.prod.yaml logs -f frontend
```

## Backups

The Postgres data lives in the `postgres_data` volume. The variables must expand
*inside* the container, so wrap the command in `sh -c` with single quotes —
otherwise your host shell substitutes them, they are empty there, and `pg_dump`
fails with `role "root" is not permitted to log in` while leaving a 0-byte file
behind:

```bash
docker compose -f docker-compose.prod.yaml exec -T db \
  sh -c 'pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB"' > backup-$(date +%F).sql

# Always check the dump is non-empty before relying on it.
ls -lh backup-*.sql
```

`*.sql` is gitignored, so a dump written into the checkout will not dirty the
working tree or risk being committed — the dumps carry real hirer details and
token rows. Move it off the host once taken; a backup sitting on the machine it
protects is not a backup.

### The private resource files

`backend/resources/system-prompt.md` and `contact.md` are gitignored. They are
therefore in no commit and no clone, and the production host is their only
copy — if the server is lost, they are gone, and the backend **will not start**
without a system prompt (see step 4 of "First deployment").

Run this from your workstation, not the server; a backup that lives on the box
it is protecting is not a backup:

```bash
scripts/backup-private-resources.sh
```

It writes a timestamped copy to `~/backups/workchat/`, verifies each file
against the host by SHA-256, and points `~/backups/workchat/latest` at the run.
It exits non-zero and skips the `latest` symlink if anything mismatches, so a
truncated transfer cannot masquerade as a good backup. Override `BACKUP_HOST`,
`BACKUP_REMOTE_DIR` or `BACKUP_DEST` if your setup differs.

To restore onto a rebuilt host:

```bash
scp ~/backups/workchat/latest/{system-prompt.md,contact.md} \
  aicv-prod:/root/ai-cv/backend/resources/
sudo chown -R 1000:1000 backend/resources   # on the host, per step 6
```

`~/backups` is still one machine. For the system prompt in particular —
unrecoverable and not reproducible from anything else — keep a second copy
somewhere off this workstation as well.

## Notes

- `NEXT_PUBLIC_API_URL` is baked into the frontend at build time as `/api`
  so the browser hits the same origin (no CORS surface for normal traffic).
- `/docs`, `/redoc`, `/openapi.json` are disabled when `DEV_MODE=0`.
- The backend and Postgres are not exposed on the host — only Caddy is.
