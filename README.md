# DaLeoBanks - Autonomous AI Agent

DaLeoBanks is a production-grade, self-evolving AI agent that operates on Twitter/X. The stack pairs a Python FastAPI backend (agent logic, scheduler, persona management) with a Node/Express + Vite frontend that proxies requests to the backend.

## Features
- 24/7 autonomous operation with persona-driven content generation
- Thompson-sampling optimization, analytics, and reflection loops
- FastAPI backend with REST and WebSocket support
- React + Vite frontend served through an Express proxy that also spawns the backend

## Prerequisites
- Python 3.11+
- Node.js 18+
- Twitter/X API credentials (for live posting)
- OpenAI API key

## Environment variables
Copy `.env.example` to `.env` and fill in the required secrets:

```bash
cp .env.example .env
```

Key variables:
- **OPENAI_API_KEY** and **X_* tokens** for LLM + Twitter access
- **ADMIN_TOKEN** and **JWT_SECRET** for admin/auth endpoints
- **LIVE** toggles autonomous posting; keep `false` for local testing
- **PORT/BACKEND_PORT** control the Express proxy and Python backend ports
- **PLATFORM_WEIGHTS, ENABLE_* flags** tune platform routing and feature toggles

## Installation
Install dependencies once per machine:

```bash
# Python (creates local venv)
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# Node
npm install
```

## Running locally
The Express dev server will spawn the FastAPI backend and proxy requests.

```bash
# From the project root
source venv/bin/activate
npm run dev
```

- Frontend + proxy: http://localhost:${PORT:-5000}
- Backend direct (if needed): http://localhost:${BACKEND_PORT:-5001}

### Production build
Bundle the frontend/server and run in production mode:

```bash
npm run build
NODE_ENV=production PORT=5000 BACKEND_PORT=5001 npm start
```

## Replit deployment
A ready-to-use configuration is included:
- `.replit` launches `scripts/replit-start.sh`, which installs Python/Node deps and starts the combined stack.
- `replit.nix` ensures Python 3.11 and Node 20 are available.

Steps:
1) Create a Replit from this repo.
2) Add a `.env` using `.env.example` as a template (set API keys and tokens).
3) Click **Run**. Express listens on port 5000 and spawns FastAPI on 5001.

## Health checks & smoke tests
After the stack is running:
- Backend health: `curl http://localhost:5001/api/health`
- Proxied health (through Express): `curl http://localhost:5000/api/health`
- Config snapshot: `curl http://localhost:5001/config`

## Project structure
- `app.py` – FastAPI application and scheduler bootstrap
- `server/index.ts` – Express/Vite server that spawns and proxies the backend
- `client/` – React frontend
- `services/` – Backend services (e.g., persona, analytics, websearch)
- `scripts/` – Replit helper scripts

## Safety & operations notes
- Keep `LIVE=false` until credentials and guardrails are fully validated.
- Update `ALLOWED_ORIGINS` and `ALLOWED_IPS` before exposing publicly.
- Rotate `ADMIN_TOKEN` and `JWT_SECRET` regularly in production.
