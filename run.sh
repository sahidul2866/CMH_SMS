#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# On Windows, run this script from Git Bash, MSYS2, or Cygwin. The native
# launcher handles Windows virtual-environment paths, prerequisite installation,
# port cleanup, and opening the application in the default browser.
case "$(uname -s)" in
  MINGW*|MSYS*|CYGWIN*)
    WINDOWS_LAUNCHER="$PROJECT_DIR/RUN_WINDOWS.bat"
    [[ -f "$WINDOWS_LAUNCHER" ]] || {
      echo "Windows launcher not found: $WINDOWS_LAUNCHER"
      exit 1
    }
    command -v cmd.exe >/dev/null 2>&1 || {
      echo "cmd.exe was not found. Run this script from Git Bash, MSYS2, or Cygwin on Windows."
      exit 1
    }
    if command -v cygpath >/dev/null 2>&1; then
      WINDOWS_LAUNCHER_NATIVE="$(cygpath -w "$WINDOWS_LAUNCHER")"
    else
      WINDOWS_LAUNCHER_NATIVE="$WINDOWS_LAUNCHER"
    fi
    echo "Windows detected; starting RUN_WINDOWS.bat..."
    # Prevent MSYS from rewriting cmd.exe switches or the already-native path.
    export MSYS2_ARG_CONV_EXCL="*"
    exec cmd.exe /d /s /c "call \"$WINDOWS_LAUNCHER_NATIVE\""
    ;;
esac

BACKEND_DIR="$PROJECT_DIR/backend"
FRONTEND_DIR="$PROJECT_DIR/frontend"
VENV_DIR="$BACKEND_DIR/.venv"
BACKEND_PORT=8100
ENV_FILE="$PROJECT_DIR/.env"

random_hex() {
  if command -v openssl >/dev/null 2>&1; then
    openssl rand -hex "$1"
  else
    "$PYTHON_BIN" -c "import secrets; print(secrets.token_hex($1))"
  fi
}

postgres_admin_psql() {
  if [[ "$(uname -s)" == "Linux" ]]; then
    sudo -u postgres psql "$@"
  else
    psql postgres "$@"
  fi
}

postgres_admin_createdb() {
  if [[ "$(uname -s)" == "Linux" ]]; then
    sudo -u postgres createdb "$@"
  else
    createdb "$@"
  fi
}

ensure_postgres() {
  if command -v pg_isready >/dev/null 2>&1 &&
     pg_isready -h 127.0.0.1 -p 5432 >/dev/null 2>&1 &&
     postgres_admin_psql -tAc "SELECT 1" >/dev/null 2>&1; then
    echo "Using the running native PostgreSQL service."
    return
  fi
  if [[ "$(uname -s)" == "Linux" ]]; then
    if ! command -v psql >/dev/null 2>&1; then
      command -v apt-get >/dev/null 2>&1 || {
        echo "Automatic PostgreSQL installation currently supports Debian/Ubuntu servers."
        exit 1
      }
      echo "Installing native PostgreSQL..."
      sudo apt-get update
      sudo apt-get install -y postgresql postgresql-contrib
    fi
    sudo systemctl enable --now postgresql
  elif [[ "$(uname -s)" == "Darwin" ]]; then
    command -v brew >/dev/null 2>&1 || {
      echo "Homebrew is required to install native PostgreSQL on macOS."
      exit 1
    }
    if ! brew list --versions postgresql@17 >/dev/null 2>&1; then
      echo "Installing native PostgreSQL 17..."
      HOMEBREW_NO_AUTO_UPDATE=1 NONINTERACTIVE=1 brew install postgresql@17
    fi
    export PATH="$(brew --prefix postgresql@17)/bin:$PATH"
    brew services start postgresql@17 >/dev/null
  else
    echo "Native PostgreSQL bootstrap is supported on Linux and macOS."
    exit 1
  fi

  echo "Waiting for native PostgreSQL..."
  for _ in {1..60}; do
    pg_isready -h 127.0.0.1 -p 5432 >/dev/null 2>&1 && break
    sleep 1
  done
  pg_isready -h 127.0.0.1 -p 5432 >/dev/null
}

lan_ip() {
  local detected=""
  if command -v hostname >/dev/null 2>&1; then
    detected="$(hostname -I 2>/dev/null | awk '{print $1}' || true)"
    if [[ -n "$detected" ]]; then
      echo "$detected"
      return
    fi
  fi
  if command -v ipconfig >/dev/null 2>&1; then
    ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null || true
  fi
}

free_port() {
  local port="$1"
  local pids=()
  local remaining=()
  local pid=""

  if command -v lsof >/dev/null 2>&1; then
    while IFS= read -r pid; do
      [[ "$pid" =~ ^[0-9]+$ ]] && pids+=("$pid")
    done < <(lsof -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null | sort -u || true)
  else
    echo "Cannot check port $port because lsof is unavailable."
    exit 1
  fi

  ((${#pids[@]} == 0)) && return
  echo "Port $port is in use by PID(s): ${pids[*]}. Stopping them..."
  kill -TERM "${pids[@]}" 2>/dev/null || true

  for _ in {1..20}; do
    if ! lsof -tiTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1; then
      echo "Port $port is free."
      return
    fi
    sleep 0.25
  done

  while IFS= read -r pid; do
    [[ "$pid" =~ ^[0-9]+$ ]] && remaining+=("$pid")
  done < <(lsof -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null | sort -u || true)
  if ((${#remaining[@]} > 0)); then
    echo "PID(s) ${remaining[*]} did not stop gracefully; forcing shutdown..."
    kill -KILL "${remaining[@]}" 2>/dev/null || true
  fi

  for _ in {1..20}; do
    ! lsof -tiTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1 && return
    sleep 0.25
  done
  echo "Could not free port $port."
  exit 1
}

command -v npm >/dev/null 2>&1 || { echo "Node.js and npm are required."; exit 1; }

PYTHON_BIN=""
for candidate in python3.12 python3.11 python3; do
  candidate_path="$(command -v "$candidate" 2>/dev/null || true)"
  candidate_version="$(${candidate_path:-false} -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")' 2>/dev/null || true)"
  if [[ -n "$candidate_path" && -n "$candidate_version" ]] && "$candidate_path" -c 'import sys; raise SystemExit(sys.version_info < (3, 11))'; then
    PYTHON_BIN="$candidate_path"
    break
  fi
done
[[ -n "$PYTHON_BIN" ]] || { echo "Python 3.11 or newer is required."; exit 1; }

if [[ ! -f "$ENV_FILE" ]]; then
  DB_PASSWORD="$(random_hex 18)"
  ADMIN_PASSWORD="$(random_hex 10)"
  cat >"$ENV_FILE" <<EOF
CMH_SMS_DATABASE_MODE=postgres
CMH_SMS_POSTGRES_DB=cmh_sms
CMH_SMS_POSTGRES_USER=cmh_sms
CMH_SMS_POSTGRES_PASSWORD=$DB_PASSWORD
CMH_SMS_POSTGRES_PORT=5432
CMH_SMS_DATABASE_URL=postgresql+psycopg://cmh_sms:$DB_PASSWORD@127.0.0.1:5432/cmh_sms
CMH_SMS_ADMIN_USERNAME=admin
CMH_SMS_ADMIN_PASSWORD=$ADMIN_PASSWORD
CMH_SMS_AUDIO_ENABLED=true
CMH_SMS_ENVIRONMENT=development
CMH_SMS_ALLOWED_HOSTS=localhost,127.0.0.1
CMH_SMS_PUBLIC_HTTPS=false
CMH_SMS_COOKIE_SECURE=false
CMH_SMS_SEED_DEMO=false
EOF
  chmod 600 "$ENV_FILE"
  echo "Created secure deployment configuration: $ENV_FILE"
  echo "Initial administrator login: admin / $ADMIN_PASSWORD"
  echo "Store this password securely; it will not be printed again."
fi

set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

if [[ "${CMH_SMS_DATABASE_MODE:-postgres}" == "postgres" ]]; then
  [[ "$CMH_SMS_POSTGRES_USER" =~ ^[a-zA-Z_][a-zA-Z0-9_]*$ ]] || { echo "Invalid PostgreSQL role name."; exit 1; }
  [[ "$CMH_SMS_POSTGRES_DB" =~ ^[a-zA-Z_][a-zA-Z0-9_]*$ ]] || { echo "Invalid PostgreSQL database name."; exit 1; }
  [[ "$CMH_SMS_POSTGRES_PASSWORD" =~ ^[a-fA-F0-9]+$ ]] || { echo "PostgreSQL password must be hexadecimal."; exit 1; }
  ensure_postgres
  echo "Creating/updating the native PostgreSQL role and database..."
  postgres_admin_psql -v ON_ERROR_STOP=1 -c "DO \$\$ BEGIN IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '$CMH_SMS_POSTGRES_USER') THEN CREATE ROLE $CMH_SMS_POSTGRES_USER LOGIN PASSWORD '$CMH_SMS_POSTGRES_PASSWORD'; ELSE ALTER ROLE $CMH_SMS_POSTGRES_USER WITH LOGIN PASSWORD '$CMH_SMS_POSTGRES_PASSWORD'; END IF; END \$\$;" >/dev/null
  if ! postgres_admin_psql -tAc "SELECT 1 FROM pg_database WHERE datname = '$CMH_SMS_POSTGRES_DB'" | grep -q 1; then
    postgres_admin_createdb -O "$CMH_SMS_POSTGRES_USER" "$CMH_SMS_POSTGRES_DB"
  fi
  export CMH_SMS_POSTGRES_PORT=5432
  export CMH_SMS_DATABASE_URL="postgresql+psycopg://$CMH_SMS_POSTGRES_USER:$CMH_SMS_POSTGRES_PASSWORD@127.0.0.1:5432/$CMH_SMS_POSTGRES_DB"
fi

if [[ ! -x "$VENV_DIR/bin/python" ]]; then
  echo "Creating standalone Python environment..."
  "$PYTHON_BIN" -m venv "$VENV_DIR"
elif ! "$VENV_DIR/bin/python" -c 'import sys; raise SystemExit(sys.version_info < (3, 11))'; then
  ARCHIVED_VENV="$BACKEND_DIR/.venv-incompatible-$(date +%Y%m%d%H%M%S)"
  echo "Archiving incompatible Python environment to $(basename "$ARCHIVED_VENV")..."
  mv "$VENV_DIR" "$ARCHIVED_VENV"
  echo "Creating standalone Python environment..."
  "$PYTHON_BIN" -m venv "$VENV_DIR"
fi

echo "Installing backend dependencies..."
"$VENV_DIR/bin/pip" install -q -r "$BACKEND_DIR/requirements.txt"

# The Meta MMS Bengali model is downloaded only on its first setup. Once the
# model is present, both synthesis and every subsequent application start are
# fully offline. Resolve relative overrides from the backend directory because
# that is also the server process's working directory.
OFFLINE_MODEL_DIR="${CMH_SMS_OFFLINE_TTS_MODEL:-$BACKEND_DIR/data/models/mms-tts-ben}"
if [[ "$OFFLINE_MODEL_DIR" != /* ]]; then
  OFFLINE_MODEL_DIR="$BACKEND_DIR/$OFFLINE_MODEL_DIR"
fi
export CMH_SMS_OFFLINE_TTS_MODEL="$OFFLINE_MODEL_DIR"

NEURAL_RUNTIME_READY=true
if ! "$VENV_DIR/bin/python" -c 'import torch, transformers, scipy, sentencepiece' >/dev/null 2>&1; then
  echo "Installing the natural offline Bengali neural voice runtime..."
  if ! "$VENV_DIR/bin/pip" install -q -r "$BACKEND_DIR/requirements-windows-audio.txt"; then
    NEURAL_RUNTIME_READY=false
    echo "WARNING: Neural voice runtime installation failed. Basic offline speech remains available."
  fi
fi

if ! find "$OFFLINE_MODEL_DIR" -maxdepth 1 -type f -name 'model*.safetensors' -print -quit 2>/dev/null | grep -q .; then
  if [[ "$NEURAL_RUNTIME_READY" == "true" ]]; then
    echo "Downloading the Meta MMS Bengali model for permanent offline use..."
  fi
  if [[ "$NEURAL_RUNTIME_READY" != "true" ]] || ! "$VENV_DIR/bin/python" -c 'from huggingface_hub import snapshot_download; import sys; snapshot_download("facebook/mms-tts-ben", local_dir=sys.argv[1])' "$OFFLINE_MODEL_DIR"; then
    echo "WARNING: Neural model download failed. Basic offline speech remains available."
    echo "         Connect to the internet and run ./run.sh again to finish the one-time neural voice setup."
  fi
else
  echo "Natural offline Bengali neural voice is already installed."
fi

echo "Migrating the CMH_SMS database..."
(cd "$BACKEND_DIR" && "$VENV_DIR/bin/alembic" upgrade head)

echo "Loading idempotent seed data..."
(cd "$BACKEND_DIR" && "$VENV_DIR/bin/python" -m app.seed)

if [[ ! -d "$FRONTEND_DIR/node_modules" ]]; then
  echo "Installing frontend dependencies..."
  (cd "$FRONTEND_DIR" && npm ci)
fi

free_port "$BACKEND_PORT"
echo "Building the frontend for same-origin hosting..."
(cd "$FRONTEND_DIR" && npm run build)

cleanup() {
  echo
  echo "Stopping CMH Smart Serial..."
  kill "${BACKEND_PID:-}" "${NGROK_PID:-}" 2>/dev/null || true
  wait "${BACKEND_PID:-}" "${NGROK_PID:-}" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

SERVER_LAN_IP="$(lan_ip)"
if [[ -z "${CMH_SMS_ALLOWED_HOSTS:-}" ]]; then
  export CMH_SMS_ALLOWED_HOSTS="localhost,127.0.0.1"
fi
if [[ "${CMH_SMS_ENVIRONMENT:-development}" != "production" && -n "$SERVER_LAN_IP" &&
      ",${CMH_SMS_ALLOWED_HOSTS:-}," != *",$SERVER_LAN_IP,"* && "${CMH_SMS_ALLOWED_HOSTS:-}" != "*" ]]; then
  export CMH_SMS_ALLOWED_HOSTS="${CMH_SMS_ALLOWED_HOSTS:+$CMH_SMS_ALLOWED_HOSTS,}$SERVER_LAN_IP"
fi
SERVER_SCHEME="http"
UVICORN_ARGS=(app.main:app --host 0.0.0.0 --port "$BACKEND_PORT" --no-access-log)
if [[ -n "${CMH_SMS_TLS_CERTFILE:-}" || -n "${CMH_SMS_TLS_KEYFILE:-}" ]]; then
  [[ -f "${CMH_SMS_TLS_CERTFILE:-}" && -f "${CMH_SMS_TLS_KEYFILE:-}" ]] || {
    echo "Both CMH_SMS_TLS_CERTFILE and CMH_SMS_TLS_KEYFILE must reference readable files."
    exit 1
  }
  export CMH_SMS_PUBLIC_HTTPS=true
  export CMH_SMS_COOKIE_SECURE=true
  SERVER_SCHEME="https"
  UVICORN_ARGS+=(--ssl-certfile "$CMH_SMS_TLS_CERTFILE" --ssl-keyfile "$CMH_SMS_TLS_KEYFILE")
fi
echo "Starting CMH Smart Serial at $SERVER_SCHEME://0.0.0.0:$BACKEND_PORT ..."
(cd "$BACKEND_DIR" && "$VENV_DIR/bin/uvicorn" "${UVICORN_ARGS[@]}") &
BACKEND_PID=$!

if [[ "${CMH_SMS_NGROK:-false}" == "true" ]]; then
  command -v ngrok >/dev/null 2>&1 || { echo "CMH_SMS_NGROK=true but ngrok is not installed."; exit 1; }
  echo "Starting optional ngrok tunnel..."
  ngrok http "$BACKEND_PORT" &
  NGROK_PID=$!
fi

echo "Frontend, API, WebSocket and server-PC audio are running from one host."
if [[ -n "$SERVER_LAN_IP" ]]; then
  echo "Open $SERVER_SCHEME://$SERVER_LAN_IP:$BACKEND_PORT from every wired radiographer and reception PC."
else
  echo "Open $SERVER_SCHEME://SERVER-PC-IP:$BACKEND_PORT from every wired radiographer and reception PC."
fi
echo "Press Ctrl+C to stop."
wait "$BACKEND_PID"
