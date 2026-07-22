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
FRONTEND_PORT=4300

free_port() {
  local port="$1"
  local pids=""

  if command -v lsof >/dev/null 2>&1; then
    pids="$(lsof -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null | sort -u || true)"
  else
    echo "Cannot check port $port because lsof is unavailable."
    exit 1
  fi

  [[ -z "$pids" ]] && return
  echo "Port $port is in use by PID(s): ${pids//$'\n'/ }. Stopping them..."
  kill $pids 2>/dev/null || true

  for _ in {1..20}; do
    sleep 0.25
    if ! lsof -tiTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1; then
      return
    fi
  done

  pids="$(lsof -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null | sort -u || true)"
  if [[ -n "$pids" ]]; then
    echo "Port $port did not stop gracefully; force-stopping PID(s): ${pids//$'\n'/ }."
    kill -KILL $pids 2>/dev/null || true
  fi
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

echo "Migrating the CMH_SMS database..."
(cd "$BACKEND_DIR" && "$VENV_DIR/bin/alembic" upgrade head)

echo "Loading idempotent seed data..."
(cd "$BACKEND_DIR" && "$VENV_DIR/bin/python" -m app.seed)

if [[ ! -d "$FRONTEND_DIR/node_modules" ]]; then
  echo "Installing frontend dependencies..."
  (cd "$FRONTEND_DIR" && npm ci)
fi

free_port "$BACKEND_PORT"
free_port "$FRONTEND_PORT"

cleanup() {
  echo
  echo "Stopping CMH Smart Serial..."
  kill "${BACKEND_PID:-}" "${FRONTEND_PID:-}" 2>/dev/null || true
  wait "${BACKEND_PID:-}" "${FRONTEND_PID:-}" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

echo "Starting API at http://127.0.0.1:$BACKEND_PORT ..."
(cd "$BACKEND_DIR" && "$VENV_DIR/bin/uvicorn" app.main:app --reload --host 127.0.0.1 --port "$BACKEND_PORT") &
BACKEND_PID=$!

echo "Starting UI at http://127.0.0.1:$FRONTEND_PORT ..."
(cd "$FRONTEND_DIR" && npm start -- --host 127.0.0.1 --port "$FRONTEND_PORT") &
FRONTEND_PID=$!

echo "CMH Smart Serial is starting. Press Ctrl+C to stop both services."
wait "$BACKEND_PID" "$FRONTEND_PID"
