#!/usr/bin/env bash
#
# One-shot setup for the GitHub Actions deploy: mint a deploy key, install it on
# the server, and set the four secrets the workflow needs.
#
# Run this from your machine, once. It is not a cron job like its neighbours —
# it lives here so the steps are executable rather than a list in a document
# somebody retypes slightly differently.
#
# Nothing it creates is written into this repository, and no secret is ever
# echoed: values reach `gh` on stdin, so they stay out of your shell history,
# your terminal and any scrollback you might later paste somewhere.
#
# Usage:
#   scripts/setup-deploy-secrets.sh --host chat.example.com --user deploy
#
# Options:
#   --host        server hostname or IP                        (required)
#   --user        SSH user that can run docker compose there    (required)
#   --repo-dir    checkout on the server        (default: /root/ai-cv)
#   --health-url  URL polled after deploying (default: https://<host>/api/health)
#   --key         key path            (default: ~/.ssh/workchat_deploy)
#   --dry-run     show what would happen, change nothing

set -euo pipefail

HOST="" USER_="" REPO_DIR="/root/ai-cv" HEALTH_URL="" DRY_RUN=0
KEY="$HOME/.ssh/workchat_deploy"

while [ $# -gt 0 ]; do
  case "$1" in
    --host) HOST="$2"; shift 2 ;;
    --user) USER_="$2"; shift 2 ;;
    --repo-dir) REPO_DIR="$2"; shift 2 ;;
    --health-url) HEALTH_URL="$2"; shift 2 ;;
    --key) KEY="$2"; shift 2 ;;
    --dry-run) DRY_RUN=1; shift ;;
    -h|--help) sed -n '2,25p' "$0" | sed 's/^# \?//'; exit 0 ;;
    *) echo "unknown option: $1" >&2; exit 1 ;;
  esac
done

[ -n "$HOST" ] || { echo "--host is required" >&2; exit 1; }
[ -n "$USER_" ] || { echo "--user is required" >&2; exit 1; }
# /api/health, not /health: Caddy proxies /api/* to the backend and everything
# else to the frontend, so /health reaches Next.js and 404s. Pass --health-url
# explicitly when the certificate is for a domain rather than this address.
[ -n "$HEALTH_URL" ] || HEALTH_URL="https://${HOST}/api/health"

case "$KEY" in
  "$PWD"/*|./*|scripts/*)
    # The repo is public. .gitignore covers id_* and *.pem, but the surest way
    # not to publish a private key is not to create one next to a checkout.
    echo "Refusing to write a private key inside the repository. Use ~/.ssh." >&2
    exit 1 ;;
esac

log() { echo "[$(date +%H:%M:%S)] $*"; }
run() { if [ "$DRY_RUN" -eq 1 ]; then echo "  would run: $*"; else "$@"; fi; }

command -v gh >/dev/null 2>&1 || {
  cat >&2 <<'MSG'
The GitHub CLI is not installed, and it is what sets the secrets.

  Fedora        sudo dnf install gh
  Debian/Ubuntu sudo apt install gh
  macOS         brew install gh

Then: gh auth login
MSG
  exit 1
}
gh auth status >/dev/null 2>&1 || { echo "gh is not logged in. Run: gh auth login" >&2; exit 1; }

# 1. Key ---------------------------------------------------------------------
if [ -f "$KEY" ]; then
  log "reusing existing key at $KEY"
else
  log "generating a deploy key at $KEY"
  run ssh-keygen -t ed25519 -N "" -C "github-actions deploy for $(basename "$PWD")" -f "$KEY"
fi

# 2. Install the public half -------------------------------------------------
# Checked first so the script is idempotent, and because ssh-copy-id has to
# authenticate somehow: with the key already authorised it would fall back to the
# agent, which on a machine with a confirm-protected key means an interactive
# prompt this script cannot answer. IdentitiesOnly keeps the probe to this key
# alone rather than letting the agent answer for it.
if ssh -i "$KEY" -o IdentitiesOnly=yes -o BatchMode=yes -o ConnectTimeout=10 \
     "${USER_}@${HOST}" true 2>/dev/null; then
  log "key already authorised for ${USER_}@${HOST} — nothing to install"
else
  log "installing the public key for ${USER_}@${HOST}"
  run ssh-copy-id -i "${KEY}.pub" "${USER_}@${HOST}"
fi

# 3. Pin the host key --------------------------------------------------------
log "scanning the host key"
if [ "$DRY_RUN" -eq 1 ]; then
  echo "  would run: ssh-keyscan $HOST"
  KNOWN_HOSTS="(host keys)"
else
  KNOWN_HOSTS="$(ssh-keyscan "$HOST" 2>/dev/null)"
  [ -n "$KNOWN_HOSTS" ] || { echo "ssh-keyscan returned nothing for $HOST" >&2; exit 1; }
fi

# 4. Prove the key works before handing it to CI -----------------------------
log "checking the key can reach docker compose on the server"
if [ "$DRY_RUN" -eq 0 ]; then
  ssh -i "$KEY" -o IdentitiesOnly=yes -o BatchMode=yes -o StrictHostKeyChecking=accept-new \
    "${USER_}@${HOST}" "cd '$REPO_DIR' && docker compose version >/dev/null" \
    || { echo "Could not run docker compose in $REPO_DIR as $USER_." >&2; exit 1; }
  log "  reachable"
fi

# 5. Secrets -----------------------------------------------------------------
# Every value goes in on stdin. None is passed as an argument, so none appears
# in `ps`, in shell history, or on screen.
log "setting repository secrets"
if [ "$DRY_RUN" -eq 1 ]; then
  echo "  would set secrets: DEPLOY_HOST DEPLOY_USER DEPLOY_SSH_KEY DEPLOY_KNOWN_HOSTS"
  echo "  would set variables: DEPLOY_REPO_DIR DEPLOY_HEALTH_URL"
else
  printf '%s' "$HOST"          | gh secret set DEPLOY_HOST
  printf '%s' "$USER_"         | gh secret set DEPLOY_USER
  gh secret set DEPLOY_SSH_KEY < "$KEY"
  printf '%s\n' "$KNOWN_HOSTS" | gh secret set DEPLOY_KNOWN_HOSTS
  printf '%s' "$REPO_DIR"      | gh variable set DEPLOY_REPO_DIR
  printf '%s' "$HEALTH_URL"    | gh variable set DEPLOY_HEALTH_URL
fi

log "done"
cat <<MSG

Set: DEPLOY_HOST, DEPLOY_USER, DEPLOY_SSH_KEY, DEPLOY_KNOWN_HOSTS
     DEPLOY_REPO_DIR=${REPO_DIR}, DEPLOY_HEALTH_URL=${HEALTH_URL}

The private key stays at ${KEY} and was never printed. Anyone holding it can
restart production, so treat it as you would a root password.

Merging to main now deploys after CI goes green. To require an approval first,
add a reviewer to the "production" environment in repo settings.
MSG
