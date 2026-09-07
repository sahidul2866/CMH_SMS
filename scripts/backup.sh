#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${CMH_SMS_ENV_FILE:-$PROJECT_DIR/.env}"
BACKUP_DIR="${CMH_SMS_BACKUP_DIR:-$PROJECT_DIR/backups}"
RETENTION_DAYS="${CMH_SMS_BACKUP_RETENTION_DAYS:-30}"

[[ -f "$ENV_FILE" ]] || { echo "Configuration not found: $ENV_FILE"; exit 1; }
set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

[[ "${CMH_SMS_DATABASE_URL:-}" == postgresql* ]] || {
  echo "Production backups require a PostgreSQL CMH_SMS_DATABASE_URL."
  exit 1
}
command -v pg_dump >/dev/null 2>&1 || { echo "pg_dump is required."; exit 1; }

mkdir -p "$BACKUP_DIR"
chmod 700 "$BACKUP_DIR"
timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
target="$BACKUP_DIR/cmh_sms_$timestamp.dump"
temporary="$target.partial"
dump_url="${CMH_SMS_DATABASE_URL/postgresql+psycopg:/postgresql:}"

pg_dump --format=custom --file="$temporary" "$dump_url"
chmod 600 "$temporary"
mv "$temporary" "$target"
find "$BACKUP_DIR" -type f -name 'cmh_sms_*.dump' -mtime "+$RETENTION_DAYS" -delete
echo "Backup created: $target"
