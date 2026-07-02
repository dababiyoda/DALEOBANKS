#!/usr/bin/env bash
set -euo pipefail

# Replit's base environment configures pip for --user installs, which is
# incompatible with a virtualenv (pip aborts with "Can not perform a
# '--user' install"). Force installs into the venv.
export PIP_USER=0

# Install Python dependencies if needed
if [ ! -d "venv" ]; then
  python3 -m venv venv
fi
source venv/bin/activate
pip install --upgrade pip >/dev/null
pip install -r requirements.txt >/dev/null

# Install Node dependencies. Check for the tsx binary rather than the
# node_modules folder so an interrupted install self-repairs on next run.
if [ ! -x "node_modules/.bin/tsx" ]; then
  npm install >/dev/null
fi

# Start the combined dev stack (Express/Vite + FastAPI backend)
BACKEND_PORT=${BACKEND_PORT:-5001}
PORT=${PORT:-5000}
NODE_ENV=${NODE_ENV:-development}
export BACKEND_PORT PORT NODE_ENV
npm run dev
