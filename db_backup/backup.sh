#!/usr/bin/env bash
set -euo pipefail

: "${POSTGRES_HOST:?POSTGRES_HOST is required}"
: "${POSTGRES_DB:?POSTGRES_DB is required}"
: "${POSTGRES_USER:?POSTGRES_USER is required}"
: "${POSTGRES_PASSWORD:?POSTGRES_PASSWORD is required}"

BACKUP_DIR="${BACKUP_DIR:-/backups}"
INTERVAL="${BACKUP_INTERVAL_SECONDS:-300}"

mkdir -p "$BACKUP_DIR"

export PGPASSWORD="$POSTGRES_PASSWORD"

echo "db_backup started. Writing dumps to $BACKUP_DIR every ${INTERVAL}s" >&2

while true; do
  ts="$(date -u +%Y%m%dT%H%M%SZ)"
  out="$BACKUP_DIR/univoice_${POSTGRES_DB}_${ts}.sql"

  echo "[$(date -u +%FT%TZ)] Running pg_dump -> $out" >&2
  pg_dump -h "$POSTGRES_HOST" -U "$POSTGRES_USER" -d "$POSTGRES_DB" > "$out"

  # Keep only the newest N backups (default 20)
  keep="${BACKUP_KEEP_LAST:-20}"
  ls -1t "$BACKUP_DIR"/*.sql 2>/dev/null | tail -n "+$((keep+1))" | xargs -r rm -f

  sleep "$INTERVAL"
done
