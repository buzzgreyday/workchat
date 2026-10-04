#!/usr/bin/env bash
#
# Deletes guest-trial rows from before today (UTC).
#
# Each row holds a keyed hash of a visitor's address, under a key for its own
# day. The backend already deletes earlier days whenever someone asks for a
# trial; this is what makes "gone when the day is over" true on a day nobody
# does. See docs/privacy.md.
#
# Runs on the production host from cron, shortly after midnight UTC.
#
# Usage:
#   scripts/purge-trial-requests.sh [--dry-run]
#
# Overrides:
#   REPO_DIR       checkout on the host (default: /opt/ai-cv)
#   COMPOSE_FILE   compose file (default: docker-compose.prod.yaml)

set -euo pipefail

REPO_DIR="${REPO_DIR:-/opt/ai-cv}"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.prod.yaml}"
DRY_RUN=0

if [ "${1:-}" = "--dry-run" ]; then
  DRY_RUN=1
fi

cd "$REPO_DIR"

log() { echo "[$(date +%FT%T)] $*"; }

# The day is UTC on both sides: the backend keys trials by UTC date.
if [ "$DRY_RUN" -eq 1 ]; then
  sql="SELECT count(*) FROM trial_requests
       WHERE day < (now() AT TIME ZONE 'UTC')::date;"
  log "dry run: counting trial rows from before today (UTC)"
else
  sql="DELETE FROM trial_requests
       WHERE day < (now() AT TIME ZONE 'UTC')::date;"
  log "deleting trial rows from before today (UTC)"
fi

# The variables must expand inside the container: the host shell has no
# POSTGRES_USER and would silently pass empty strings to psql.
result="$(docker compose -f "$COMPOSE_FILE" exec -T db \
  sh -c "psql -tA -U \"\$POSTGRES_USER\" -d \"\$POSTGRES_DB\" -c \"${sql}\"")"

log "done: ${result}"
