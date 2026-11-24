#!/usr/bin/env bash
# Linux / macOS dev launcher for StudyFlow AI.
# Usage: bash scripts/run-dev.sh [backend_port] [frontend_port]
set -euo pipefail

BACKEND_PORT="${1:-4000}"
FRONTEND_PORT="${2:-5173}"

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BACKEND_DIR="$ROOT/backend"
FRONTEND_DIR="$ROOT/frontend"

# ----- Check prerequisites -----
if ! command -v node &>/dev/null; then
  echo "[ERROR] node is not on PATH. Install Node.js first." >&2
  exit 1
fi
if command -v python3 &>/dev/null; then
  PY="python3"
elif command -v python &>/dev/null; then
  PY="python"
else
  echo "[ERROR] python3 / python is not on PATH. Install Python first." >&2
  exit 1
fi

# ----- Install frontend deps if missing -----
if [ ! -d "$FRONTEND_DIR/node_modules" ]; then
  echo "[frontend] node_modules not found. Running npm install..."
  (cd "$FRONTEND_DIR" && npm install)
fi

# ----- Install backend deps if missing -----
if [ ! -d "$BACKEND_DIR/.venv" ]; then
  echo "[backend] .venv not found. Creating virtual environment..."
  "$PY" -m venv "$BACKEND_DIR/.venv"
  echo "[backend] Installing pip dependencies..."
  "$BACKEND_DIR/.venv/bin/pip" install -r "$BACKEND_DIR/requirements.txt" --quiet
fi

# ----- Trap cleanup -----
CLEANUP_PIDS=()
cleanup() {
  echo ""
  echo "Stopping StudyFlow dev servers..."
  for pid in "${CLEANPE_PIDS[@]:-}"; do
    # Check if variable is set and not empty, and process exists
    if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
      kill "$pid" 2>/dev/null || true
    fi
  done
  wait 2>/dev/null || true
  echo "Done."
}
# Make sure array is initialized to avoid unbound variable issues
CLEANUP_PIDS=()
cleanup() {
  echo ""
  echo "Stopping StudyFlow dev servers..."
  for pid in ${CLEANUP_PIDS[@]+"${CLEANUP_PIDS[@]}"}; do
    if kill -0 "$pid" 2>/dev/null; then
      kill "$pid" 2>/dev/null || true
    fi
  done
  wait 2>/dev/null || true
  echo "Done."
}
trap cleanup EXIT INT TERM

BACKEND_API="http://localhost:$BACKEND_PORT"

# ----- Start backend -----
echo "Starting backend on $BACKEND_API ..."
(cd "$BACKEND_DIR" && PORT="$BACKEND_PORT" .venv/bin/uvicorn app.main:app \
  --host 0.0.0.0 --port "$BACKEND_PORT" --reload --no-access-log) &
CLEANUP_PIDS+=($!)

# ----- Start frontend -----
echo "Starting frontend on http://localhost:$FRONTEND_PORT ..."
(cd "$FRONTEND_DIR" && VITE_API_BASE_URL="$BACKEND_API" npx vite \
  --host 0.0.0.0 --port "$FRONTEND_PORT") &
CLEANUP_PIDS+=($!)

echo ""
echo "StudyFlow dev servers:"
echo "  Backend:  $BACKEND_API"
echo "  Frontend: http://localhost:$FRONTEND_PORT"
echo "Press Ctrl+C to stop both."
echo ""

wait
