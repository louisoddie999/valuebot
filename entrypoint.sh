#!/usr/bin/env bash
# Runs the auto-refresh loop AND the API in one container.
set -u
cd /app
PORT="${PORT:-8000}"; SCOPE="${SCOPE:-ahead}"; REFRESH_HOURS="${REFRESH_HOURS:-12}"
BOARD="${BOARD:-2000}"; ENRICH="${ENRICH:-2000}"

echo "[entrypoint] initial refresh: scope=$SCOPE (proxy: ${SCRAPER_PROXY:+set}${SCRAPER_PROXY:-none})"
python -m src.pipeline.daily --scope "$SCOPE" --board "$BOARD" --enrich "$ENRICH" || echo "[entrypoint] initial refresh failed (continuing)"

# background auto-refresh every REFRESH_HOURS
(
  while true; do
    sleep "$(( REFRESH_HOURS * 3600 ))"
    echo "[entrypoint] scheduled refresh: scope=$SCOPE"
    python -m src.pipeline.daily --scope "$SCOPE" --board "$BOARD" --enrich "$ENRICH" || echo "[entrypoint] scheduled refresh failed"
  done
) &

echo "[entrypoint] serving API on :$PORT"
exec uvicorn api.main:app --host 0.0.0.0 --port "$PORT"
