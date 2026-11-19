#!/usr/bin/env bash
set -euo pipefail
umask 077
: "${DATABASE_URL:?DATABASE_URL is required}"
: "${BACKUP_FILE:?BACKUP_FILE is required}"
if [[ ! -f "$BACKUP_FILE" ]]; then
  echo "Backup file does not exist: $BACKUP_FILE" >&2
  exit 2
fi
if [[ "${RESTORE_CONFIRM:-}" != "YES" ]]; then
  echo "Restore is destructive. Set RESTORE_CONFIRM=YES after verifying the target database and backup." >&2
  exit 3
fi
printf 'Restoring %s into the configured database.\n' "$BACKUP_FILE"
if [[ "$DATABASE_URL" == postgresql* ]]; then
  pg_restore --clean --if-exists --single-transaction --no-owner --dbname="$DATABASE_URL" "$BACKUP_FILE"
elif [[ "$DATABASE_URL" == sqlite* ]]; then
  DB_PATH="${DATABASE_URL#sqlite:///}"
  TEMP_PATH="${DB_PATH}.restore.$$"
  cp "$BACKUP_FILE" "$TEMP_PATH"
  mv "$TEMP_PATH" "$DB_PATH"
else
  echo "Unsupported DATABASE_URL for this restore helper." >&2
  exit 2
fi
echo "Restore completed. Verify application health and record counts before reopening service."
