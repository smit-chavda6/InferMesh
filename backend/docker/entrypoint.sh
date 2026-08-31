#!/bin/sh
# Apply migrations, then run the given command (uvicorn by default).
# Compose already gates startup on Postgres being healthy; the retry loop covers
# the remaining race and any transient hiccup.
set -e

echo "entrypoint: applying database migrations..."
n=0
until alembic upgrade head; do
  n=$((n + 1))
  if [ "$n" -ge 10 ]; then
    echo "entrypoint: migrations failed after $n attempts" >&2
    exit 1
  fi
  echo "entrypoint: migration attempt $n failed, retrying in 3s..."
  sleep 3
done
echo "entrypoint: migrations applied."

exec "$@"
