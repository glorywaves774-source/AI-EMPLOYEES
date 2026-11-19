#!/usr/bin/env bash
set -euo pipefail
umask 077
: "${DATABASE_URL:?DATABASE_URL is required}"
: "${BACKUP_DIR:=./backups}"
mkdir -p "$BACKUP_DIR"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
if [[ "$DATABASE_URL" == postgresql* ]]; then
  pg_dump "$DATABASE_URL" --format=custom --file="$BACKUP_DIR/ai_workforce_${STAMP}.dump"
  echo "Created $BACKUP_DIR/ai_workforce_${STAMP}.dump"
elif [[ "$DATABASE_URL" == sqlite* ]]; then
  DB_PATH="${DATABASE_URL#sqlite:///}"
  cp "$DB_PATH" "$BACKUP_DIR/ai_workforce_${STAMP}.db"
  echo "Created $BACKUP_DIR/ai_workforce_${STAMP}.db"
else
  echo "Unsupported DATABASE_URL for this backup helper." >&2
  exit 2
fi
