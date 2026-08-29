#!/usr/bin/env bash
#
# Deletes refresh-token rows that can no longer authenticate anything.
#
# Unlike chat content, these are deleted outright rather than redacted. There is
# no operational record worth keeping in an expired session — the conversations
# it produced are their own rows and are untouched — and the table grows without
# bound otherwise: every rotation inserts a row, so one hirer refreshing on a
# 15-minute access token adds roughly a hundred rows a week.
#
# Only rows past their own expiry are touched, so a live session is never cut
# from under someone mid-conversation. Revoked-but-unexpired rows are kept
# deliberately: they are what replay detection reads to tell a stolen token from
# an unknown one, and deleting them early would turn a detectable replay into a
# plain "invalid token".
#
# Runs on the production host from cron, alongside backup-db.sh.
#
# Usage:
#   scripts/purge-expired-sessions.sh [--dry-run]
#
# Overrides:
#   REPO_DIR              checkout on the host (default: /root/ai-cv)
#   COMPOSE_FILE          compose file (default: docker-compose.prod.yaml)
#   SESSION_GRACE_DAYS    days past expiry to keep (default: 7)

set -euo pipefail

REPO_DIR="${REPO_DIR:-/root/ai-cv}"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.prod.yaml}"
# A short tail past expiry, so a row is still there to explain a 401 to whoever
# is reading the logs the morning after.
DAYS="${SESSION_GRACE_DAYS:-7}"
DRY_RUN=0

if [ "${1:-}" = "--dry-run" ]; then
  DRY_RUN=1
fi

case "$DAYS" in
  ''|*[!0-9]*) echo "SESSION_GRACE_DAYS must be an integer, got '${DAYS}'" >&2; exit 1 ;;
esac

cd "$REPO_DIR"

log() { echo "[$(date +%FT%T)] $*"; }

if [ "$DRY_RUN" -eq 1 ]; then
  sql="SELECT count(*) FROM refresh_tokens
       WHERE expires_at < now() - interval '${DAYS} days';"
  log "dry run: counting sessions expired more than ${DAYS} days ago"
else
  # rotated_to is ON DELETE SET NULL, so a chain can be removed in any order and
  # a surviving predecessor simply loses its pointer. Nothing reads rotated_to
  # once a row is past expiry — the grace window that consults it is measured in
  # seconds — so the lost link costs nothing.
  sql="DELETE FROM refresh_tokens
       WHERE expires_at < now() - interval '${DAYS} days';"
  log "deleting sessions expired more than ${DAYS} days ago"
fi

# The variables must expand inside the container: the host shell has no
# POSTGRES_USER and would silently pass empty strings to psql.
result="$(docker compose -f "$COMPOSE_FILE" exec -T db \
  sh -c "psql -tA -U \"\$POSTGRES_USER\" -d \"\$POSTGRES_DB\" -c \"${sql}\"")"

log "done: ${result}"
