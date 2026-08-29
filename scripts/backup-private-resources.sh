#!/usr/bin/env bash
#
# Backs up the private CV resources that exist nowhere else.
#
# system-prompt.md and contact.md are gitignored, so they are not in the
# repository and not in any clone. The production host is their only copy —
# lose the server and they are gone. This pulls them off the box into a
# timestamped directory and verifies the copies against the source.
#
# Usage:
#   scripts/backup-private-resources.sh
#
# Override with environment variables if your setup differs:
#   BACKUP_HOST        ssh host (default: aicv-prod)
#   BACKUP_REMOTE_DIR  resources dir on the host (default: /opt/ai-cv/backend/resources)
#   BACKUP_DEST        where backups are written (default: ~/backups/workchat)

set -euo pipefail

HOST="${BACKUP_HOST:-aicv-prod}"
REMOTE_DIR="${BACKUP_REMOTE_DIR:-/opt/ai-cv/backend/resources}"
DEST_ROOT="${BACKUP_DEST:-$HOME/backups/workchat}"

FILES=(system-prompt.md contact.md)

stamp="$(date +%Y-%m-%dT%H-%M-%S)"
dest="$DEST_ROOT/$stamp"

mkdir -p "$dest"
# These are private; keep them unreadable to other local users.
chmod 700 "$DEST_ROOT" "$dest"

echo "Backing up from ${HOST}:${REMOTE_DIR}"

for f in "${FILES[@]}"; do
  scp -q "${HOST}:${REMOTE_DIR}/${f}" "${dest}/${f}"
  echo "  fetched ${f}"
done

chmod 600 "${dest}"/*

# Verify against the source rather than trusting the transfer. A silently
# truncated backup is worse than no backup, because it looks like one.
echo "Verifying..."
remote_sums="$(ssh "$HOST" "cd '${REMOTE_DIR}' && sha256sum $(printf '%s ' "${FILES[@]}")")"

failed=0
for f in "${FILES[@]}"; do
  want="$(printf '%s\n' "$remote_sums" | awk -v f="$f" '$2 == f {print $1}')"
  got="$(sha256sum "${dest}/${f}" | awk '{print $1}')"

  if [ -z "$want" ]; then
    echo "  FAIL ${f}: no checksum from host" >&2
    failed=1
  elif [ "$want" != "$got" ]; then
    echo "  FAIL ${f}: checksum mismatch" >&2
    failed=1
  else
    echo "  ok   ${f} ($(wc -c < "${dest}/${f}") bytes)"
  fi
done

if [ "$failed" -ne 0 ]; then
  echo "Backup FAILED — leaving ${dest} in place for inspection." >&2
  exit 1
fi

# Point "latest" at this run so restores do not have to guess a timestamp.
ln -sfn "$dest" "${DEST_ROOT}/latest"

echo "Backup complete: ${dest}"
echo "Restore with: scp ${DEST_ROOT}/latest/{system-prompt.md,contact.md} ${HOST}:${REMOTE_DIR}/"
