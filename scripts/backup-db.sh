#!/usr/bin/env bash
#
# Nightly full backup of the production database.
#
# Runs on the production host, from cron. The database is a few megabytes, so
# a full dump every night costs about a second and a megabyte — cheaper to run
# and far cheaper to reason about than differential backups of the same data.
#
# Retention: 7 daily, 4 weekly (Sundays), 6 monthly (the 1st).
#
# Usage:
#   scripts/backup-db.sh
#
# Overrides:
#   REPO_DIR      checkout on the host (default: /root/ai-cv)
#   COMPOSE_FILE  compose file to use (default: docker-compose.prod.yaml)
#   BACKUP_DEST   where dumps are written (default: /root/backups/workchat/db)

set -euo pipefail

REPO_DIR="${REPO_DIR:-/root/ai-cv}"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.prod.yaml}"
DEST="${BACKUP_DEST:-/root/backups/workchat/db}"

KEEP_DAILY=7
KEEP_WEEKLY=4
KEEP_MONTHLY=6

cd "$REPO_DIR"

mkdir -p "$DEST"/daily "$DEST"/weekly "$DEST"/monthly
chmod 700 "$DEST"

stamp="$(date +%F)"
out="${DEST}/daily/db-${stamp}.sql.gz"
tmp="${out}.partial"

log() { echo "[$(date +%FT%T)] $*"; }

cleanup() { rm -f "$tmp"; }
trap cleanup EXIT

log "dumping database"

# The variables must expand *inside* the container: the host shell has no
# POSTGRES_USER, and would silently pass empty strings to pg_dump. pipefail
# makes a pg_dump failure fail the whole pipeline rather than leaving a
# well-formed gzip of an error message.
docker compose -f "$COMPOSE_FILE" exec -T db \
  sh -c 'pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB"' | gzip -9 > "$tmp"

# Verify before it is allowed to look like a backup.
if ! gzip -t "$tmp" 2>/dev/null; then
  log "FAIL: dump is not valid gzip"
  exit 1
fi

if ! zcat "$tmp" | head -40 | grep -q "PostgreSQL database dump"; then
  log "FAIL: dump lacks the pg_dump header"
  exit 1
fi

if ! zcat "$tmp" | grep -q "CREATE TABLE"; then
  log "FAIL: dump contains no tables"
  exit 1
fi

size="$(wc -c < "$tmp")"

# Atomic: a partial transfer never occupies the real filename.
mv "$tmp" "$out"
chmod 600 "$out"
trap - EXIT

log "wrote ${out} (${size} bytes)"

# Promote to the longer-lived tiers. Copies rather than links, so pruning one
# tier can never remove a file another tier still depends on.
if [ "$(date +%u)" = "7" ]; then
  cp -p "$out" "${DEST}/weekly/db-${stamp}.sql.gz"
  log "promoted to weekly"
fi

if [ "$(date +%d)" = "01" ]; then
  cp -p "$out" "${DEST}/monthly/db-${stamp}.sql.gz"
  log "promoted to monthly"
fi

prune() {
  local dir="$1" keep="$2" removed
  # shellcheck disable=SC2012
  removed="$(ls -1t "$dir"/db-*.sql.gz 2>/dev/null | tail -n "+$((keep + 1))" || true)"
  if [ -n "$removed" ]; then
    echo "$removed" | xargs -r rm -f
    log "pruned $(echo "$removed" | wc -l) from $(basename "$dir")"
  fi
}

prune "${DEST}/daily" "$KEEP_DAILY"
prune "${DEST}/weekly" "$KEEP_WEEKLY"
prune "${DEST}/monthly" "$KEEP_MONTHLY"

log "done: $(ls -1 "${DEST}"/daily/*.sql.gz 2>/dev/null | wc -l) daily, \
$(ls -1 "${DEST}"/weekly/*.sql.gz 2>/dev/null | wc -l) weekly, \
$(ls -1 "${DEST}"/monthly/*.sql.gz 2>/dev/null | wc -l) monthly"
