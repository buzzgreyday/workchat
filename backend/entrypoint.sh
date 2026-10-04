#!/bin/sh
set -e

echo "Running database migrations..."
alembic upgrade head

if [ "$#" -gt 0 ]; then
    exec "$@"
else
    # No access log: it would write each visitor's address, which this app
    # keeps out of its logs (see app/common/client_ip.py). Caddy logs requests.
    exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --no-access-log
fi