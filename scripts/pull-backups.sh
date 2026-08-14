#!/usr/bin/env bash
#
# Pulls the server's backups down to this workstation.
#
# The nightly dumps live on the production host, which is the machine they
# exist to protect — they are not a backup until a copy is somewhere else.
# Run this from your workstation whenever it is on; it is incremental, so
# re-running it only transfers what is new.
#
# Covers the database dumps. The private resource files (system-prompt.md,
# contact.md) are handled by backup-private-resources.sh.
#
# Usage:
#   scripts/pull-backups.sh
#
# Overrides:
#   BACKUP_HOST         ssh host (default: aicv-prod)
#   BACKUP_REMOTE_DIR   backup dir on the host (default: /root/backups/workchat/db)
#   BACKUP_DEST         local destination (default: ~/backups/workchat/db)

set -euo pipefail

HOST="${BACKUP_HOST:-aicv-prod}"
REMOTE_DIR="${BACKUP_REMOTE_DIR:-/root/backups/workchat/db}"
DEST="${BACKUP_DEST:-$HOME/backups/workchat/db}"

mkdir -p "$DEST"
chmod 700 "$DEST"

echo "Pulling ${HOST}:${REMOTE_DIR} -> ${DEST}"

# Delete local copies the server has pruned, so the workstation mirrors the
# retention policy instead of growing without bound.
rsync -az --delete --chmod=F600 \
  "${HOST}:${REMOTE_DIR}/" "${DEST}/"

echo "Verifying against the host..."

remote_sums="$(ssh "$HOST" "cd '${REMOTE_DIR}' && find . -name '*.sql.gz' -type f -exec sha256sum {} + | sort -k2")"
local_sums="$(cd "$DEST" && find . -name '*.sql.gz' -type f -exec sha256sum {} + | sort -k2)"

if [ "$remote_sums" != "$local_sums" ]; then
  echo "FAIL: local copies do not match the host" >&2
  diff <(echo "$remote_sums") <(echo "$local_sums") || true
  exit 1
fi

count="$(printf '%s\n' "$remote_sums" | grep -c . || true)"

# A dump that cannot be decompressed is not a backup. Cheap to check here.
while IFS= read -r f; do
  [ -n "$f" ] || continue
  gzip -t "$DEST/$f" || { echo "FAIL: ${f} is corrupt locally" >&2; exit 1; }
done < <(cd "$DEST" && find . -name '*.sql.gz' -type f)

echo "OK: ${count} dumps verified"
du -sh "$DEST"
