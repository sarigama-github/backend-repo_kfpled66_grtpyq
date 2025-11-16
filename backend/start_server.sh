#!/bin/bash
set -euo pipefail

echo "Starting FastAPI backend server..."

# Kill any existing uvicorn processes or anything bound to port 8000
if command -v pkill >/dev/null 2>&1; then
  pkill -f "uvicorn .*main:app" 2>/dev/null || true
fi

# Try to free port 8000 if lsof is available
if command -v lsof >/dev/null 2>&1; then
  PIDS=$(lsof -ti:8000 || true)
  if [ -n "${PIDS}" ]; then
    echo "Freeing port 8000 from PIDs: ${PIDS}"
    kill ${PIDS} 2>/dev/null || true
    sleep 1
  fi
fi

mkdir -p logs

# Do NOT install dependencies here; the orchestrator handles it.
# Start uvicorn in the foreground so the orchestrator can manage the process.
echo "Starting FastAPI server (foreground)..."
exec uvicorn main:app --host 0.0.0.0 --port 8000
