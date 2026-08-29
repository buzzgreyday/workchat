#!/usr/bin/env bash
#
# Scrubs chat message content past the retention window.
#
# Redacts rather than deletes: the row, its counts and its timings survive, only
# the text is nulled. Deletion would take the operational record with it, and
# every foreign key in this schema is RESTRICT so rows cannot be removed
# piecemeal anyway.
#
# Runs on the production host from cron, alongside backup-db.sh.
#
# Usage:
#   scripts/purge-chat-content.sh [--dry-run]
#
# Overrides:
#   REPO_DIR              checkout on the host (default: /opt/ai-cv)
#   COMPOSE_FILE          compose file (default: docker-compose.prod.yaml)
#   CHAT_RETENTION_DAYS   days of content to keep (default: 30)

set -euo pipefail

REPO_DIR="${REPO_DIR:-/opt/ai-cv}"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.prod.yaml}"
DAYS="${CHAT_RETENTION_DAYS:-30}"
DRY_RUN=0

if [ "${1:-}" = "--dry-run" ]; then
  DRY_RUN=1
fi

case "$DAYS" in
  ''|*[!0-9]*) echo "CHAT_RETENTION_DAYS must be an integer, got '${DAYS}'" >&2; exit 1 ;;
esac

cd "$REPO_DIR"

log() { echo "[$(date +%FT%T)] $*"; }

if [ "$DRY_RUN" -eq 1 ]; then
  sql="SELECT count(*) FROM chat_messages
       WHERE content IS NOT NULL AND created_at < now() - interval '${DAYS} days';"
  log "dry run: counting content older than ${DAYS} days"
else
  # Idempotent: rows already redacted have content IS NULL and are skipped.
  sql="UPDATE chat_messages SET content = NULL, redacted_at = now()
       WHERE content IS NOT NULL AND created_at < now() - interval '${DAYS} days';"
  log "redacting content older than ${DAYS} days"
fi

# The variables must expand inside the container: the host shell has no
# POSTGRES_USER and would silently pass empty strings to psql.
result="$(docker compose -f "$COMPOSE_FILE" exec -T db \
  sh -c "psql -tA -U \"\$POSTGRES_USER\" -d \"\$POSTGRES_DB\" -c \"${sql}\"")"

log "done: ${result}"

# Conversations whose messages are all redacted get stamped too, so the admin
# list shows at a glance that a thread has been scrubbed.
if [ "$DRY_RUN" -eq 0 ]; then
  docker compose -f "$COMPOSE_FILE" exec -T db sh -c "psql -tA -U \"\$POSTGRES_USER\" -d \"\$POSTGRES_DB\" -c \"
    UPDATE conversations c SET redacted_at = now()
    WHERE c.redacted_at IS NULL
      AND EXISTS (SELECT 1 FROM chat_messages m WHERE m.conversation_id = c.id)
      AND NOT EXISTS (
        SELECT 1 FROM chat_messages m
        WHERE m.conversation_id = c.id AND m.content IS NOT NULL
      );\"" >/dev/null
  log "conversation redaction stamps updated"
fi
