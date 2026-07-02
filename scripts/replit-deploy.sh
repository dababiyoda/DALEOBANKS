#!/usr/bin/env bash
# Production entrypoint for Replit Deployments (publishing).
# Assumes the deployment build step already ran `npm ci && npm run build`
# and installed Python dependencies; installs anything missing, then runs
# the bundled production server (Express serving dist/public + FastAPI).
set -euo pipefail

if [ ! -d "venv" ]; then
  python3 -m venv venv
fi
source venv/bin/activate
pip install --quiet -r requirements.txt

if [ ! -f "dist/index.js" ] || [ ! -d "dist/public" ]; then
  npm run build
fi

export NODE_ENV=production
export PORT="${PORT:-5000}"
export BACKEND_PORT="${BACKEND_PORT:-5001}"
exec npm start
