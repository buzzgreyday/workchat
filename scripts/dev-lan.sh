#!/usr/bin/env bash
#
# Opens the local dev stack to a phone on the same network.
#
# Finds this machine's LAN address, recreates the backend and frontend
# containers with docker-compose.lan.yaml on top (so the browser is pointed at
# that address rather than at localhost, which on a phone is the phone), mints
# a claim link, and prints it with a QR code to scan. localhost:3000 keeps
# working on this machine at the same time.
#
# The chat needs a claim to open a session, so the link is the thing to open:
# the bare address gets the "ask for a link" screen. Each run mints a new one,
# at dev defaults (20 questions, a week).
#
# Usage:
#   scripts/dev-lan.sh          # open to the LAN
#   scripts/dev-lan.sh --off    # back to the plain localhost stack
#
# Overrides:
#   LAN_IP    the address to use, when the guess is the wrong interface
#             (a VPN, a second network card)
#
# Needs: docker compose, curl, python3; qrencode for the QR (optional).

set -euo pipefail

cd "$(dirname "$0")/.."

compose_base=(docker compose -f docker-compose.yaml)

if [[ "${1:-}" == "--off" ]]; then
  echo "Recreating backend and frontend without the LAN overlay..."
  "${compose_base[@]}" up -d backend frontend
  echo "Back to localhost only: http://localhost:3000"
  exit 0
fi

# The source address of the route to the internet: the interface a phone on
# the same Wi-Fi can reach, and not docker's bridges, which `hostname -I`
# would list alongside it.
LAN_IP="${LAN_IP:-$(ip -4 route get 1.1.1.1 2>/dev/null | awk '{for (i = 1; i < NF; i++) if ($i == "src") { print $(i + 1); exit }}')}"

if [[ -z "$LAN_IP" ]]; then
  echo "Could not work out this machine's LAN address. Set LAN_IP and rerun." >&2
  exit 1
fi

export LAN_IP

echo "LAN address: $LAN_IP"
echo "Recreating backend and frontend with the LAN overlay..."
"${compose_base[@]}" -f docker-compose.lan.yaml up -d backend frontend

# The admin key never leaves this script: read from the env file, sent in a
# header to the local backend, and not printed.
admin_key="$(sed -n 's/^ADMIN_KEY=//p' backend/.env | tail -n 1 | tr -d "\"'")"

if [[ -z "$admin_key" ]]; then
  echo "No ADMIN_KEY in backend/.env, so no claim link. Open http://$LAN_IP:3000" >&2
  exit 0
fi

# Recreated containers take a moment: migrations run before uvicorn starts.
echo -n "Waiting for the backend"
for _ in $(seq 1 60); do
  if curl -fsS "http://localhost:8000/health" >/dev/null 2>&1; then
    break
  fi
  echo -n "."
  sleep 1
done
echo

claim="$(
  curl -fsS -X POST "http://localhost:8000/admin/issue-token" \
    -H "Content-Type: application/json" \
    -H "X-Admin-Key: $admin_key" \
    -d '{"subject": "Local", "company": "Phone", "version": 2}' |
    python3 -c 'import json, sys; print(json.load(sys.stdin)["token"])'
)"

url="http://$LAN_IP:3000/?claim=$claim"

echo
echo "Open on your phone (same Wi-Fi):"
echo "  $url"
echo

if command -v qrencode >/dev/null 2>&1; then
  qrencode -t ANSIUTF8 "$url"
fi

cat <<EOF
The frontend takes a few seconds to compile on the first request.
Nothing loading? The phone must be on the same network, and the firewall must
allow ports 3000 and 8000 in.
Done testing: scripts/dev-lan.sh --off
EOF
