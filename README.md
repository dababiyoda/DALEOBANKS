# DaLeoBanks - Governed AI Agent

DaLeoBanks is a human-governed AI-agent implementation for bounded Twitter/X
research, drafting, optimization, approval, and optionally armed operation. The
stack pairs a Python FastAPI backend with a Node/Express + Vite frontend. Passing
tests and builds do not by themselves establish production-grade assurance.

## Features
- dry-run-by-default scheduled operation with an explicit arming ceremony
- Thompson-sampling optimization, analytics, and reflection loops
- FastAPI backend with REST and WebSocket support
- React + Vite frontend served through an Express proxy that also spawns the backend

## Prerequisites
- Python 3.11+
- Node.js 20+
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
- **JWT_ISSUER**, **JWT_AUDIENCE**, and an explicit **ALLOWED_ORIGINS** allowlist
  are mandatory when `APP_ENV=production`
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

# Node (reproducible lockfile install)
npm ci
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
- `.replit` uses module-based config (`nodejs-20`, `python-3.11`, `web`) — no `replit.nix` needed.
- The **Run** button executes the "Full Stack" workflow: `scripts/replit-start.sh` installs deps and starts the combined stack, waiting on port 5000.
- Publishing is preconfigured as a **Reserved VM** deployment (the agent is a stateful 24/7 scheduler): the build step compiles the client/server bundle and installs Python deps, and `scripts/replit-deploy.sh` runs the production stack with port 5000 mapped to 80.

Steps:
1) Create a Replit from this repo.
2) Add secrets in the Replit **Secrets** pane (`OPENAI_API_KEY`, X tokens, `ADMIN_TOKEN`, `JWT_SECRET`; see `.env.example` for the full list). Keep `LIVE` unset/false until you deliberately arm it.
3) Click **Run** for development, or **Deploy → Reserved VM** to publish. Deployment secrets are configured separately in the deployment pane.

## Health checks & smoke tests
After the stack is running:
- Backend health: `curl http://localhost:5001/api/health`
- Proxied health (through Express): `curl http://localhost:5000/api/health`

## Project structure
- `app.py` – FastAPI application and scheduler bootstrap
- `server/index.ts` – Express/Vite server that spawns and proxies the backend
- `client/` – React frontend
- `services/` – Backend services (e.g., persona, analytics, websearch)
- `scripts/` – Replit helper scripts
- `tests/` – Pytest suite (`tests/stubs/` holds offline dependency stubs)
- `docs/` – Operational documentation

## Safety & operations notes
- Keep `LIVE=false` until credentials and guardrails are fully validated.
- Production startup rejects placeholder admin/JWT secrets, missing issuer or
  audience bindings, and wildcard origins.
- Private dashboard, venture, persona, analytics, and draft reads require a
  validated identity. Consequential mutations require the admin role.
- The browser keeps the short-lived admin JWT in tab-scoped session storage;
  a public production deployment still requires independent XSS, session,
  proxy, and recovery review.
- Rotate `ADMIN_TOKEN` and `JWT_SECRET` regularly in production.
- Every publish, identity change, lesson, and gate decision is recorded in a
  tamper-evident decision ledger (`data/decision_ledger.jsonl`). A broken
  chain or repeated job failures automatically disarm live posting. See
  [docs/SAFETY_AND_ROLLOUT.md](docs/SAFETY_AND_ROLLOUT.md) for the safety
  spine and the discipline for rolling out new platforms.

## UAT sibling-service contract

DALEOBANKS can exchange a schema-1.0 `OpportunityPacket` with
`dababiyoda/WealthMachineIntelligence`, but the runtime integration is currently
held: no approved production URL, service identity, durable reconciliation, or
execution authority is configured. The ChatGPT Site may record an activation
intent; it may not store this service's secret or call it directly. See
[docs/UAT_WEBSITE_INTEGRATION.md](docs/UAT_WEBSITE_INTEGRATION.md) and
[`services/uat_integration_manifest.json`](services/uat_integration_manifest.json).

LIVE PLAYER is UAT agent context, not a DALEOBANKS connector or authority
grant, and is excluded from the current service protocol.

## Verification

```bash
pytest -q
npm run check
npm run build
npm audit --omit=dev --audit-level=high
```

The hardening branch currently passes 264 Python tests, TypeScript checking, a
production web build, and a zero-vulnerability high-severity runtime npm audit.
