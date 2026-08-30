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
secret. Caddy rate-limits `/api/admin*` to 20 requests per minute per IP, but if
you want defence in depth, restricting `/api/admin*` to a known source address at
the Caddy layer is the obvious next step — deliberately not configured here,
since a wrong address locks you out of minting tokens.

Every route that costs something is metered per client IP:

| Zone | Path | Limit | Why |
| --- | --- | --- | --- |
| `admin_zone` | `/api/admin*` | 20/min | Mints and revokes credentials |
| `auth_zone` | `/api/v2/auth*` | 30/min | Writes rows; a claim link is worth guessing at |
| `chat_zone` | `/api/chat*` | 30/min | Every call bills OpenAI |
| `session_zone` | `/api/session` | 60/min | One indexed read, no write, no model call |

**These are deliberately loose, and none of them is the access control.** That is
the signed token, the per-grant query quota and the single-use claim — and unlike
an IP counter, none of those can be confused by two people sharing an address. The
limiter only exists to cap cost and noise, so the numbers are set where they will
not fire on a real visitor: an attacker without a valid token gets a 401 before any
of this costs anything, while turning away a hiring manager is a real loss.

Sizing assumes a **shared egress IP**, which is the normal case here — a company's
hiring managers reach the site from behind one NAT address, so several people
claiming links in the same minute is ordinary use, not abuse. `session_zone` gets
the most headroom because it is the cheapest call and the most frequent: every page
load, every reload and every token rotation asks it how many questions are left.

**The keying breaks silently behind a proxy.** `key {remote_host}` is the true
client address only because Caddy terminates TLS directly. Put Cloudflare, a load
balancer or another reverse proxy in front and `remote_host` becomes *that* host,
collapsing every visitor into a single counter — the first busy visitor then
rate-limits everyone else. Nothing errors; it just starts refusing people. If you
ever front this, set `trusted_proxies` and key on the forwarded client address
instead:

```
key {http.request.header.CF-Connecting-IP}   # or X-Forwarded-For, per your proxy
```

Clients are told apart from the backend's own 429 by the response body: the backend
sends `{"detail": "Query limit reached"}` when a grant is spent, the limiter sends
none. The frontend keys off that, so a rate-limited visitor is asked to wait rather
than told their questions are gone.

**Content is scrubbed after 30 days.** Add the purge to the same crontab as the
backup:

```
30 3 * * * /usr/bin/flock -n /tmp/workchat-purge.lock /opt/ai-cv/scripts/purge-chat-content.sh >> /var/log/workchat/purge.log 2>&1
```

Override the window with `CHAT_RETENTION_DAYS` in `backend/.env`. See
`docs/database.md` for the erasure order and the backup caveat.

**Expired sessions are pruned too.** Only relevant once you issue `version=2`
links — `refresh_tokens` stays empty otherwise — but harmless to add either way:

```
45 3 * * * /usr/bin/flock -n /tmp/workchat-sessions.lock /opt/ai-cv/scripts/purge-expired-sessions.sh >> /var/log/workchat/purge.log 2>&1
```

Override the tail it keeps with `SESSION_GRACE_DAYS`. Both scripts take
`--dry-run`, which counts instead of writing.

**Revoking access.** `POST /api/admin/tokens/{token_id}/revoke` with your admin
key kills a grant and every session under it, v1 links included. Revoking the
grant is the part that matters for a v2 link: cutting sessions alone would leave
anyone still holding the claim URL able to open a fresh one.

## CI/CD

`.github/workflows/ci.yml` runs on every push and pull request: backend types
(mypy) and tests, frontend types, lint and production build, an
apply-and-drift-check of the migrations against a real Postgres, a Caddyfile
adapt using the custom rate-limit build, a secret scan over the full history, and
both Docker images.

`.github/workflows/deploy.yml` then deploys **main** to production automatically.
It triggers on CI *completing successfully*, not on push — `workflow_run` is what
orders the two, where `on: push` would race them.

### Secrets it needs

Set these under **Settings → Secrets and variables → Actions**. Until every one
of them exists the deploy job logs a warning and skips, so merging to main stays
green while this is unconfigured.

| secret | what it is |
| --- | --- |
| `DEPLOY_HOST` | Hostname or IP of the server |
| `DEPLOY_USER` | SSH user with permission to run `docker compose` there. Use a dedicated non-root account — see below |
| `DEPLOY_SSH_KEY` | Private half of a keypair whose public half is in that user's `authorized_keys` |
| `DEPLOY_KNOWN_HOSTS` | Output of `ssh-keyscan <host>`, pinning the host key |

And as **variables** (not secrets — neither is sensitive):

| variable | default | what it is |
| --- | --- | --- |
| `DEPLOY_REPO_DIR` | `/opt/ai-cv` | Checkout on the server |
| `DEPLOY_HEALTH_URL` | *(unset)* | URL polled after deploying; unset means deploy without verifying |

### The deploy account

Deploy as a dedicated non-root user. The key sits in GitHub Actions secrets, so
its blast radius is whatever that account can do; as root that is everything on
the box, and there is no reason for CI to need that much.

```bash
useradd --create-home --shell /bin/bash deploy
usermod -aG docker deploy          # docker group == able to run the stack
usermod -p '*' deploy              # no password can authenticate
```

Use `usermod -p '*'`, **not** `passwd -l`. Both look like "lock the account", but
`passwd -l` writes `!` to the shadow field and sshd then refuses the account
outright — key and all — logging `User deploy not allowed because account is
locked`. `*` means no password can ever authenticate while leaving key auth
working, which is what a deploy account wants.

The checkout has to live somewhere that user can own, so it is `/opt/ai-cv`
rather than under `/root`. Moving it is safe because `docker-compose.prod.yaml`
pins `name: ai-cv` — the compose project name, the container names and the
`ai-cv_postgres_data` volume all come from that, not from the directory. Without
that pin, moving the directory would rename the project and silently start
against an empty database.

Two things follow the move: `chown -R deploy:deploy` on the checkout, and root's
crontab, whose backup and purge entries carry absolute paths.

`scripts/setup-deploy-secrets.sh` does all six in one go — mints the key,
installs it, pins the host key, proves the key can actually run `docker compose`
there, and sets everything:

```bash
scripts/setup-deploy-secrets.sh --host chat.example.com --user deploy
scripts/setup-deploy-secrets.sh --host chat.example.com --user deploy --dry-run   # look first
```

It needs the GitHub CLI (`gh auth login`). Values reach `gh` on stdin rather than
as arguments, so none of them lands in `ps`, your shell history or your
scrollback, and the private key is never printed at all. It refuses to write a
key inside the repository: `.gitignore` covers `id_ed25519*` and `*.pem`, but the
surest way not to publish a private key is not to create one next to a public
checkout.

By hand, if you would rather:

```bash
ssh-keygen -t ed25519 -f ~/.ssh/workchat_deploy -C "github-actions deploy"
ssh-copy-id -i ~/.ssh/workchat_deploy.pub <user>@<host>
ssh-keyscan <host>            # -> DEPLOY_KNOWN_HOSTS
cat ~/.ssh/workchat_deploy    # -> DEPLOY_SSH_KEY (the private half)
```

Either way, give that key the narrowest access you are willing to: it can restart
production.

### Releases

After a successful deploy, a third job tags and publishes a GitHub Release — but
only if the version changed. It reads `version` from `backend/pyproject.toml`; if
`v<version>` is not already released it creates the tag and a release with
auto-generated notes, and otherwise says so and stops.

The number stays your decision. Nothing infers it from commit messages, so
cutting a release is the same `chore(release):` commit you already make:

```bash
# bump the version, commit, merge to main
sed -i 's/^version = ".*"/version = "0.2.0"/' backend/pyproject.toml
git commit -am "chore(release): 0.2.0"
```

The release runs **after** the deploy, and only when the deploy actually ran —
the deploy job reports whether it deployed or skipped for missing secrets, and
the release job checks that. So a tag on GitHub always means the same thing: it
built, it deployed, and it answered a health check. A release that was never
deployed would be worse than no release, because it reads as a claim about
production that is not true.

### Why the deploy job is written the way it is

This repository is public, which makes two things load-bearing rather than
stylistic:

- **Secrets reach the shell through `env:`, never `${{ }}` inside `run:`.**
  Interpolating a secret into a `run:` block pastes the value into the generated
  script, where a trace or a crafted argument can surface it; masking only covers
  what the runner recognises on the way out.
- **The job checks the run came from this repository and was not a pull request.**
  `workflow_run` is privileged — it executes in the base repo with secrets no
  matter who triggered the run it followed. The `branches: [main]` filter alone
  is not enough, because anyone can fork, push a branch named `main`, and open a
  PR whose CI run then carries `head_branch: main`.

The CI workflow itself uses no secrets at all, which is what makes it safe to run
on pull requests from forks. Keep it that way: a check that needs a credential
belongs in the deploy workflow or behind an environment.

### Turning the auto-deploy into approve-then-deploy

The deploy job declares `environment: production`. Adding a required reviewer to
that environment in repo settings gates every deploy behind an approval without
editing the workflow.

---

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

It connects as the deploy user, which is all the read access it needs — the
resources directory is owned by `deploy`. That wants its own alias, because the
`aicv-prod` one pins root's key with `IdentitiesOnly yes` and so cannot
authenticate as anyone else:

```
Host aicv-deploy
    HostName <your host>
    User deploy
    IdentityFile ~/.ssh/workchat_deploy
    IdentitiesOnly yes
```

`pull-backups.sh` stays on `aicv-prod`: the database dumps land in
`/root/backups`, which the deploy user cannot read.

To restore onto a rebuilt host:

```bash
scp ~/backups/workchat/latest/{system-prompt.md,contact.md} \
  aicv-deploy:/opt/ai-cv/backend/resources/
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
