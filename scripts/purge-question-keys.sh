#!/usr/bin/env bash
#
# Deletes question keys older than a day.
#
# A key is what lets a failed question be retried for free, and each row holds a
# hash of that question. Nobody retries a question from yesterday, so nothing is
# gained by keeping them. See docs/privacy.md.
#
# Runs on the production host from cron, nightly.
#
# Usage:
#   scripts/purge-question-keys.sh [--dry-run]
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

if [ "$DRY_RUN" -eq 1 ]; then
  sql="SELECT count(*) FROM question_keys
       WHERE created_at < now() - interval '1 day';"
  log "dry run: counting question keys older than a day"
else
  sql="DELETE FROM question_keys
       WHERE created_at < now() - interval '1 day';"
  log "deleting question keys older than a day"
fi

# The variables must expand inside the container: the host shell has no
# POSTGRES_USER and would silently pass empty strings to psql.
result="$(docker compose -f "$COMPOSE_FILE" exec -T db \
  sh -c "psql -tA -U \"\$POSTGRES_USER\" -d \"\$POSTGRES_DB\" -c \"${sql}\"")"

log "done: ${result}"
