#!/usr/bin/env bash
set -Eeuo pipefail
IFS=$'\n\t'

readonly ACCOUNT_HOME="${HOME:?HOME is not set}"
readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly DEFAULT_RELEASE_ZIP="$SCRIPT_DIR/rqms-release.zip"
readonly RELEASE_ZIP="${1:-${DEFAULT_RELEASE_ZIP:-$ACCOUNT_HOME/rqms-release.zip}}"
readonly APP_ROOT="$ACCOUNT_HOME/rqms-app"
readonly DOC_ROOT="$ACCOUNT_HOME/public_html/rqms"
readonly APP_ENV="$ACCOUNT_HOME/.cmh-sms.env"
readonly MANAGED_VENV="$ACCOUNT_HOME/rqms-venv"
readonly STAMP="$(date +%Y%m%d-%H%M%S)"
readonly STAGE="$ACCOUNT_HOME/.rqms-stage-$STAMP"
readonly APP_BACKUP="$ACCOUNT_HOME/rqms-app-backup-$STAMP"
readonly DOC_BACKUP="$ACCOUNT_HOME/rqms-docroot-backup-$STAMP"
readonly DB_BACKUP="$ACCOUNT_HOME/rqms-db-backup-$STAMP.dump"
readonly PUBLIC_URL="https://rqms.digidrivetechnology.com"
readonly CPANEL_DB_NAME="digidriv_rqms"
readonly CPANEL_DB_USER="digidriv_rqms_user"

log() { printf '\n\033[1;34m==> %s\033[0m\n' "$1"; }
fail() { printf '\n\033[1;31mERROR: %s\033[0m\n' "$1" >&2; exit 1; }
urlencode() {
  local input="$1"
  local output=""
  local character=""
  local index
  local LC_ALL=C
  for ((index = 0; index < ${#input}; index++)); do
    character="${input:index:1}"
    case "$character" in
      [a-zA-Z0-9.~_-]) output+="$character" ;;
      *) printf -v output '%s%%%02X' "$output" "'$character" ;;
    esac
  done
  printf '%s' "$output"
}
cleanup() {
  if [ -d "$STAGE" ]; then
    find "$STAGE" -mindepth 1 -delete 2>/dev/null || true
    rmdir "$STAGE" 2>/dev/null || true
  fi
}
trap cleanup EXIT

remove_tree() {
  local target="$1"
  [ -d "$target" ] || return 0
  find "$target" -mindepth 1 -delete
  rmdir "$target"
}

rollback_deployment() {
  log "Rolling back failed deployment"
  remove_tree "$APP_ROOT"
  remove_tree "$DOC_ROOT"
  [ -d "$APP_BACKUP" ] && mv "$APP_BACKUP" "$APP_ROOT"
  [ -d "$DOC_BACKUP" ] && mv "$DOC_BACKUP" "$DOC_ROOT"
  if [ -f "$DB_BACKUP" ]; then
    PGPASSWORD="$PGPASSWORD" pg_restore --clean --if-exists --no-owner --no-privileges \
      --single-transaction --exit-on-error --host="$PGHOST" --port="$PGPORT" \
      --username="$PGUSER" --dbname="$PGDATABASE" "$DB_BACKUP" || \
      printf 'WARNING: automatic database rollback failed; restore %s manually.\n' "$DB_BACKUP" >&2
  fi
  [ -d "$APP_ROOT/backend/tmp" ] && touch "$APP_ROOT/backend/tmp/restart.txt"
}

parse_pg_url() {
  local database_url="${CMH_SMS_DATABASE_URL:-}"
  [ -n "$database_url" ] || return 0
  [[ "$database_url" == postgresql* ]] || return 0

  local url_without_scheme="${database_url#*://}"
  local auth_part="${url_without_scheme%@*}"
  local host_and_db="${url_without_scheme#*@}"
  local host_part="${host_and_db%%/*}"
  local db_path="${host_and_db#*/}"
  local database_name="${db_path%%\?*}"

  if [ "$auth_part" != "$url_without_scheme" ]; then
    local username="${auth_part%%:*}"
    local password="${auth_part#*:}"
    if [ -n "$username" ] && [ -n "$password" ]; then
      export PGUSER="${PGUSER:-$username}"
      export PGPASSWORD="${PGPASSWORD:-$password}"
    fi
  fi

  local host_name="$host_part"
  local port_number="5432"
  if [[ "$host_part" == *:* ]]; then
    host_name="${host_part%:*}"
    port_number="${host_part##*:}"
  fi

  export PGHOST="${PGHOST:-$host_name}"
  export PGPORT="${PGPORT:-$port_number}"
  export PGDATABASE="${PGDATABASE:-$database_name}"
}

ensure_postgres_database() {
  parse_pg_url

  local db_host="${PGHOST:-127.0.0.1}"
  local db_port="${PGPORT:-5432}"
  local db_user="${PGUSER:-${CMH_SMS_POSTGRES_USER:-$CPANEL_DB_USER}}"
  local db_name="${PGDATABASE:-${CMH_SMS_POSTGRES_DB:-$CPANEL_DB_NAME}}"
  local db_password="${PGPASSWORD:-${CMH_SMS_POSTGRES_PASSWORD:-}}"

  [ -n "$db_password" ] || fail "PostgreSQL password is missing. Set CMH_SMS_POSTGRES_PASSWORD or CMH_SMS_DATABASE_URL."

  export PGHOST="$db_host"
  export PGPORT="$db_port"
  export PGUSER="$db_user"
  export PGDATABASE="$db_name"
  export PGPASSWORD="$db_password"

  local ready=false
  for attempt in 1 2 3; do
    if PGPASSWORD="$db_password" psql -h "$db_host" -p "$db_port" -U "$db_user" -d "$db_name" -tAc "SELECT 1" >/dev/null 2>&1; then
      ready=true
      break
    fi

    if command -v psql >/dev/null 2>&1; then
      if ! PGPASSWORD="$db_password" psql -h "$db_host" -p "$db_port" -U "$db_user" -d postgres -tAc "SELECT 1 FROM pg_roles WHERE rolname = '$db_user'" | grep -q 1; then
        PGPASSWORD="$db_password" psql -h "$db_host" -p "$db_port" -U "$db_user" -d postgres -v ON_ERROR_STOP=1 -c "DO \$\$ BEGIN IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '$db_user') THEN CREATE ROLE $db_user LOGIN PASSWORD '$db_password'; ELSE ALTER ROLE $db_user WITH LOGIN PASSWORD '$db_password'; END IF; END \$\$;" >/dev/null 2>&1 || true
      fi
      if ! PGPASSWORD="$db_password" psql -h "$db_host" -p "$db_port" -U "$db_user" -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname = '$db_name'" | grep -q 1; then
        if command -v createdb >/dev/null 2>&1; then
          createdb -h "$db_host" -p "$db_port" -U "$db_user" -O "$db_user" "$db_name" >/dev/null 2>&1 || true
        fi
        PGPASSWORD="$db_password" psql -h "$db_host" -p "$db_port" -U "$db_user" -d postgres -v ON_ERROR_STOP=1 -c "SELECT 'CREATE DATABASE \"$db_name\" OWNER \"$db_user\"' WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = '$db_name')\\gexec" >/dev/null 2>&1 || true
      fi
    fi

    if PGPASSWORD="$db_password" psql -h "$db_host" -p "$db_port" -U "$db_user" -d "$db_name" -tAc "SELECT 1" >/dev/null 2>&1; then
      ready=true
      break
    fi
    sleep 2
  done

  [ "$ready" = "true" ] || fail "PostgreSQL database '$db_name' could not be created or reached on $db_host:$db_port."
  printf 'Database ready: %s on %s:%s\n' "$db_name" "$db_host" "$db_port"
}

retry_db_bootstrap() {
  local attempt
  for attempt in 1 2 3; do
    if (
      set -a
      # shellcheck disable=SC1091
      source "$STAGE/backend/.env"
      set +a
      cd "$STAGE/backend"
      current_revision="$("$PYTHON_BIN" -m alembic current 2>/dev/null | awk 'NF { value=$1 } END { print value }')"
      head_revision="$("$PYTHON_BIN" -m alembic heads 2>/dev/null | awk 'NF { value=$1 } END { print value }')"
      if [ -n "$current_revision" ] && [ "$current_revision" = "$head_revision" ]; then
        printf 'Database already at Alembic head %s; migrations skipped.\n' "$head_revision"
      else
        "$PYTHON_BIN" -m alembic upgrade head
      fi
      "$PYTHON_BIN" -m app.seed
    ); then
      return 0
    fi

    if ! (PGPASSWORD="${PGPASSWORD:-${CMH_SMS_POSTGRES_PASSWORD:-}}" psql -h "${PGHOST:-127.0.0.1}" -p "${PGPORT:-5432}" -U "${PGUSER:-${CMH_SMS_POSTGRES_USER:-$CPANEL_DB_USER}}" -d "${PGDATABASE:-${CMH_SMS_POSTGRES_DB:-$CPANEL_DB_NAME}}" -tAc "SELECT 1" >/dev/null 2>&1); then
      log "Database missing or unreachable; creating it before retrying bootstrap."
      ensure_postgres_database
    fi
    printf 'Bootstrap attempt %s failed; retrying in 3 seconds...\n' "$attempt" >&2
    sleep 3
  done

  fail "Database migrations and seed failed after 3 attempts."
}

restore_production_snapshot() {
  local snapshot="$STAGE/database/production.dump"
  [ -f "$snapshot" ] || fail "Release is missing database/production.dump"
  command -v pg_dump >/dev/null 2>&1 || fail "pg_dump is unavailable."
  command -v pg_restore >/dev/null 2>&1 || fail "pg_restore is unavailable."

  log "Backing up target production database"
  PGPASSWORD="$PGPASSWORD" pg_dump --format=custom --no-owner --no-privileges \
    --host="$PGHOST" --port="$PGPORT" --username="$PGUSER" --dbname="$PGDATABASE" \
    --file="$DB_BACKUP"
  chmod 600 "$DB_BACKUP"

  log "Restoring bundled production database"
  PGPASSWORD="$PGPASSWORD" pg_restore --clean --if-exists --no-owner --no-privileges \
    --single-transaction --exit-on-error --host="$PGHOST" --port="$PGPORT" \
    --username="$PGUSER" --dbname="$PGDATABASE" "$snapshot"
}

set_env() {
  local key="$1"
  local value="$2"
  local file="$3"
  local escaped_value="${value//\\/\\\\}"
  escaped_value="${escaped_value//&/\\&}"
  escaped_value="${escaped_value//#/\\#}"
  if grep -q "^${key}=" "$file"; then
    sed -i "s#^${key}=.*#${key}=${escaped_value}#" "$file"
  else
    printf '%s=%s\n' "$key" "$value" >> "$file"
  fi
}

configure_cpanel_database() {
  local supplied_password="${CMH_SMS_POSTGRES_PASSWORD:-}"
  local saved_password=""
  if [ -f "$APP_ENV" ]; then
    saved_password="$(sed -n 's/^CMH_SMS_POSTGRES_PASSWORD=//p' "$APP_ENV" | tail -n 1)"
  fi

  local db_password="${supplied_password:-$saved_password}"
  if [ -z "$db_password" ] && [ -t 0 ]; then
    read -r -s -p "cPanel PostgreSQL password for $CPANEL_DB_USER: " db_password
    printf '\n'
  fi
  [ -n "$db_password" ] || fail "Set CMH_SMS_POSTGRES_PASSWORD to the password assigned to cPanel user '$CPANEL_DB_USER'."

  local encoded_db_password
  encoded_db_password="$(urlencode "$db_password")"
  set_env CMH_SMS_POSTGRES_DB "$CPANEL_DB_NAME" "$APP_ENV"
  set_env CMH_SMS_POSTGRES_USER "$CPANEL_DB_USER" "$APP_ENV"
  set_env CMH_SMS_POSTGRES_PASSWORD "$db_password" "$APP_ENV"
  set_env CMH_SMS_DATABASE_URL "postgresql+psycopg://$CPANEL_DB_USER:$encoded_db_password@127.0.0.1:5432/$CPANEL_DB_NAME" "$APP_ENV"
  chmod 600 "$APP_ENV"
}

create_default_app_env() {
  if [ -f "$APP_ENV" ]; then
    return 0
  fi

  local admin_password
  if command -v openssl >/dev/null 2>&1; then
    admin_password="$(openssl rand -hex 12)"
  else
    admin_password="$(LC_ALL=C od -An -N12 -tx1 /dev/urandom | tr -d ' \n')"
  fi

  cat > "$APP_ENV" <<EOF
CMH_SMS_DATABASE_MODE=postgres
CMH_SMS_POSTGRES_DB=$CPANEL_DB_NAME
CMH_SMS_POSTGRES_USER=$CPANEL_DB_USER
CMH_SMS_POSTGRES_PASSWORD=
CMH_SMS_POSTGRES_PORT=5432
CMH_SMS_DATABASE_URL=
CMH_SMS_ADMIN_USERNAME=admin
CMH_SMS_ADMIN_PASSWORD=$admin_password
CMH_SMS_AUDIO_ENABLED=false
CMH_SMS_ENVIRONMENT=production
CMH_SMS_ALLOWED_HOSTS=rqms.digidrivetechnology.com
CMH_SMS_PUBLIC_HTTPS=true
CMH_SMS_COOKIE_SECURE=true
CMH_SMS_CORS_ORIGINS=
CMH_SMS_SEED_DEMO=false
EOF
  chmod 600 "$APP_ENV"
  printf 'Created self-contained deployment environment: %s\n' "$APP_ENV"
  printf 'Initial administrator login: admin / %s\n' "$admin_password"
}

log "Preflight"
preflight_errors=()
[ "$ACCOUNT_HOME" = "/home/digidriv" ] || preflight_errors+=("Unexpected account home: $ACCOUNT_HOME")
[ "$SCRIPT_DIR" = "$DOC_ROOT" ] || preflight_errors+=("Upload deploy-rqms.sh and rqms-release.zip to $DOC_ROOT, then run the script from there.")
[ -f "$RELEASE_ZIP" ] || preflight_errors+=("Missing release ZIP: $RELEASE_ZIP")
[ -d "$ACCOUNT_HOME/public_html" ] || preflight_errors+=("Missing cPanel public_html directory: $ACCOUNT_HOME/public_html")
for required_command in unzip curl crontab pg_dump pg_restore psql awk grep sed find; do
  command -v "$required_command" >/dev/null 2>&1 || preflight_errors+=("Required command is unavailable: $required_command")
done
if [ -f "$RELEASE_ZIP" ] && command -v unzip >/dev/null 2>&1; then
  if ! unzip -tq "$RELEASE_ZIP" >/dev/null 2>&1; then
    preflight_errors+=("Release ZIP is corrupt or unreadable: $RELEASE_ZIP")
  else
    for required in backend/passenger_wsgi.py backend/requirements.txt backend/alembic.ini backend/app/main.py frontend/dist/cmh-smart-serial/browser/index.html database/production.dump; do
      unzip -Z1 "$RELEASE_ZIP" | awk -v item="$required" '$0==item{found=1} END{exit !found}' || preflight_errors+=("Release ZIP missing $required")
    done
  fi
fi
if [ "${#preflight_errors[@]}" -gt 0 ]; then
  printf '\n\033[1;31mPreflight found %s problem(s):\033[0m\n' "${#preflight_errors[@]}" >&2
  for preflight_error in "${preflight_errors[@]}"; do
    printf '  - %s\n' "$preflight_error" >&2
  done
  exit 1
fi

create_default_app_env
configure_cpanel_database

PYTHON_BIN=""
python_supported() {
  local interpreter="$1"
  [ -x "$interpreter" ] && "$interpreter" -c 'import sys; raise SystemExit(sys.version_info < (3, 11))' >/dev/null 2>&1
}

PYTHON_CANDIDATES="$(find -L "$ACCOUNT_HOME/virtualenv" -maxdepth 9 \( -type f -o -type l \) -path '*/bin/python*' 2>/dev/null | sort || true)"
while IFS= read -r candidate; do
  [ -n "$candidate" ] || continue
  case "$candidate" in
    *rqms*|*cmh_sms*|*cmh-sms*) python_supported "$candidate" && PYTHON_BIN="$candidate" && break ;;
  esac
done <<PYTHON_PATHS
$PYTHON_CANDIDATES
PYTHON_PATHS

if [ -z "$PYTHON_BIN" ] && python_supported "$MANAGED_VENV/bin/python"; then
  PYTHON_BIN="$MANAGED_VENV/bin/python"
fi

if [ -z "$PYTHON_BIN" ]; then
  BASE_PYTHON=""
  python_search_paths=""
  for command_name in python3.12 python3.11 python3 python; do
    command_path="$(command -v "$command_name" 2>/dev/null || true)"
    [ -n "$command_path" ] && python_search_paths+="$command_path"$'\n'
  done
  python_search_paths+="/opt/alt/python312/bin/python3"$'\n'
  python_search_paths+="/opt/alt/python311/bin/python3"$'\n'
  python_search_paths+="/opt/alt/python313/bin/python3"$'\n'
  python_search_paths+="/usr/local/bin/python3.12"$'\n'
  python_search_paths+="/usr/local/bin/python3.11"$'\n'
  python_search_paths+="/usr/bin/python3.12"$'\n'
  python_search_paths+="/usr/bin/python3.11"$'\n'
  while IFS= read -r candidate; do
    [ -n "$candidate" ] || continue
    if python_supported "$candidate"; then
      BASE_PYTHON="$candidate"
      break
    fi
  done <<PYTHON_SEARCH_PATHS
$python_search_paths
PYTHON_SEARCH_PATHS

  [ -n "$BASE_PYTHON" ] || fail "Python 3.11+ was not found. Enable a Python 3.11 or 3.12 package in cPanel, then rerun this script."
  if [ -d "$MANAGED_VENV" ] && ! python_supported "$MANAGED_VENV/bin/python"; then
    mv "$MANAGED_VENV" "$ACCOUNT_HOME/rqms-venv-incompatible-$STAMP"
  fi
  if [ ! -x "$MANAGED_VENV/bin/python" ]; then
    log "Creating dedicated Python environment"
    "$BASE_PYTHON" -m venv "$MANAGED_VENV" || fail "Could not create $MANAGED_VENV with $BASE_PYTHON. Enable the Python venv module in cPanel."
  fi
  PYTHON_BIN="$MANAGED_VENV/bin/python"
fi

printf 'Using Python: %s\n' "$PYTHON_BIN"

log "Preparing complete application"
mkdir "$STAGE"
unzip -q "$RELEASE_ZIP" -d "$STAGE"
cp "$APP_ENV" "$STAGE/backend/.env"
chmod 600 "$STAGE/backend/.env"
set_env CMH_SMS_ENVIRONMENT production "$STAGE/backend/.env"
set_env CMH_SMS_ALLOWED_HOSTS rqms.digidrivetechnology.com "$STAGE/backend/.env"
set_env CMH_SMS_PUBLIC_HTTPS true "$STAGE/backend/.env"
set_env CMH_SMS_COOKIE_SECURE true "$STAGE/backend/.env"
set_env CMH_SMS_CORS_ORIGINS '' "$STAGE/backend/.env"
set_env CMH_SMS_AUDIO_ENABLED false "$STAGE/backend/.env"
set_env CMH_SMS_FRONTEND_DIST "$APP_ROOT/frontend/dist/cmh-smart-serial/browser" "$STAGE/backend/.env"

log "Installing dependencies"
"$PYTHON_BIN" -m pip install --disable-pip-version-check -r "$STAGE/backend/requirements.txt"
"$PYTHON_BIN" -m compileall -q "$STAGE/backend/app" "$STAGE/backend/passenger_wsgi.py"

log "Applying database migrations and seed"
ensure_postgres_database
restore_production_snapshot
retry_db_bootstrap

log "Creating Passenger document root"
mkdir "$STAGE/document-root"
{
  printf 'PassengerEnabled On\n'
  printf 'PassengerAppRoot "%s/backend"\n' "$APP_ROOT"
  printf 'PassengerBaseURI "/"\n'
  printf 'PassengerAppType wsgi\n'
  printf 'PassengerStartupFile passenger_wsgi.py\n'
  printf 'PassengerPython "%s"\n' "$PYTHON_BIN"
  printf 'PassengerAppLogFile "%s/rqms-passenger.log"\n' "$ACCOUNT_HOME"
} > "$STAGE/document-root/.htaccess"
find "$STAGE/backend" "$STAGE/frontend" -type d -exec chmod 755 {} \;
find "$STAGE/backend" "$STAGE/frontend" -type f -exec chmod 644 {} \;
chmod 600 "$STAGE/backend/.env"
chmod 644 "$STAGE/document-root/.htaccess"

log "Backing up current deployment"
[ -d "$APP_ROOT" ] && mv "$APP_ROOT" "$APP_BACKUP"
[ -d "$DOC_ROOT" ] && mv "$DOC_ROOT" "$DOC_BACKUP"

log "Publishing RQMS"
mkdir "$APP_ROOT"
mv "$STAGE/backend" "$APP_ROOT/backend"
mv "$STAGE/frontend" "$APP_ROOT/frontend"
mv "$STAGE/document-root" "$DOC_ROOT"
mkdir -p "$APP_ROOT/backend/tmp"
touch "$APP_ROOT/backend/tmp/restart.txt"

log "Installing fault-tolerance watchdog"
cat > "$APP_ROOT/health-watchdog.sh" <<'WATCHDOG'
#!/usr/bin/env bash
set -u
readonly APP_ROOT="$HOME/rqms-app"
readonly HEALTH_URL="https://rqms.digidrivetechnology.com/api/v1/health"
readonly STATE_DIR="$APP_ROOT/backend/tmp"
readonly FAILURE_FILE="$STATE_DIR/health-failures"
readonly LOCK_DIR="$STATE_DIR/health-watchdog.lock"
readonly LOG_FILE="$HOME/rqms-health-watchdog.log"

mkdir -p "$STATE_DIR"
mkdir "$LOCK_DIR" 2>/dev/null || exit 0
trap 'rmdir "$LOCK_DIR" 2>/dev/null || true' EXIT

status="$(curl -L -sS -o /dev/null --connect-timeout 8 --max-time 20 -w '%{http_code}' "$HEALTH_URL" || true)"
if [ "$status" = "200" ]; then
  printf '0\n' > "$FAILURE_FILE"
  exit 0
fi

failures=0
[ -f "$FAILURE_FILE" ] && read -r failures < "$FAILURE_FILE"
case "$failures" in (*[!0-9]*|'') failures=0 ;; esac
failures=$((failures + 1))
printf '%s\n' "$failures" > "$FAILURE_FILE"
printf '%s health check failed (HTTP %s), consecutive failures: %s\n' \
  "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "${status:-ERR}" "$failures" >> "$LOG_FILE"

if [ "$failures" -ge 3 ]; then
  touch "$STATE_DIR/restart.txt"
  printf '%s Passenger restart requested.\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" >> "$LOG_FILE"
  printf '0\n' > "$FAILURE_FILE"
fi
WATCHDOG
chmod 700 "$APP_ROOT/health-watchdog.sh"

watchdog_marker="# CMH_RQMS_HEALTH_WATCHDOG"
watchdog_cron="* * * * * $APP_ROOT/health-watchdog.sh >/dev/null 2>&1 $watchdog_marker"
existing_crontab="$(crontab -l 2>/dev/null || true)"
filtered_crontab="$(printf '%s\n' "$existing_crontab" | grep -vF "$watchdog_marker" || true)"
printf '%s\n%s\n' "$filtered_crontab" "$watchdog_cron" | awk 'NF' | crontab -

log "Checking production"
health_status=""
for attempt in 1 2 3 4 5; do
  health_status="$(curl -L -sS -o /dev/null --max-time 20 -w '%{http_code}' "$PUBLIC_URL/api/v1/health" || true)"
  [ "$health_status" = "200" ] && break
  sleep 3
done
page_status="$(curl -L -sS -o /dev/null --max-time 30 -w '%{http_code}' "$PUBLIC_URL/" || true)"
if [ "$health_status" != "200" ] || [ "$page_status" != "200" ]; then
  rollback_deployment
  fail "Production checks failed (health ${health_status:-ERR}, page ${page_status:-ERR}); previous application and database restored."
fi

printf '\nRQMS deployment successful: %s\n' "$PUBLIC_URL"
[ -d "$APP_BACKUP" ] && printf 'Application backup: %s\n' "$APP_BACKUP"
[ -d "$DOC_BACKUP" ] && printf 'Document-root backup: %s\n' "$DOC_BACKUP"
printf 'Pre-restore database backup: %s\n' "$DB_BACKUP"
