#!/usr/bin/env bash
set -euo pipefail

# Install Python dependencies if needed
if [ ! -d "venv" ]; then
  python3 -m venv venv
fi
source venv/bin/activate
pip install --upgrade pip >/dev/null
pip install -r requirements.txt >/dev/null

# Install Node dependencies (idempotent)
if [ ! -d "node_modules" ]; then
  npm install >/dev/null
fi

# Start the combined dev stack (Express/Vite + FastAPI backend)
BACKEND_PORT=${BACKEND_PORT:-5001}
PORT=${PORT:-5000}
NODE_ENV=${NODE_ENV:-development}
export BACKEND_PORT PORT NODE_ENV
npm run dev
