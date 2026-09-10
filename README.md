# DaLeoBanks - Autonomous AI Agent

## SR-001 shared bridge recovery (draft, 2026-09-08)

This bounded repair starts from main ed5e95d7f48e006d180b972efe138179325c31d2.
Historical operating claims below are not established by this package. No live
Twitter/X operation, deployment, credentials, founder authentication, economic
outcome, CMC or VDM is authorized or claimed here.

The consumer imports one canonical Kernel boundary package, revision
3e059c20331d96e05a44daac1b097896aaabde93 (uniimente-kernel-boundaries 0.1.1), pinned
in requirements.txt and pyproject.toml. services/bridge_security.py and
services/kernel_contracts.py are temporary import adapters, not security mirrors;
their headers define source, owner, supported versions, expiry/removal and refusal.
Kernel contracts/adapters/events/provenance own shared meaning and durable truth.
DALEOBANKS retains its domain models and consumer composition. The old transport
and translation implementations remain in Git as historical alternatives.

WMI #33 requires JWT plus signed-body admission. The linked WMI consumer draft
retains both checks and adds transport v2 context/response binding and durable
idempotency. This producer supplies an explicitly configured synthetic JWT,
signs the exact body, refuses redirects, verifies the actual response bytes and
context, and preserves returned identity, observation time and dissent. It never
issues credentials. Shared keys prove possession only, not isolation or Alfonso's
identity. Missing keys/JWT/state/anchor/principal, unsupported protocol or schema,
tampering and conflicting identities fail closed. A retry has a new transport
nonce with the same logical operation key and payload; response replay protection
survives consumer-process replacement.

HTTP mode is allowed only in explicit synthetic-localhost composition. The
required test settings are UNIIMENTE_BRIDGE_MODE=synthetic-localhost, a loopback
WEALTHMACHINE_URL, and isolated signing/JWT/state/constitutional-anchor/principal
fixtures. These settings authorize no live routing. Direct organ HTTP remains
refused until canonical Kernel mediation is composed and reviewed. Do not weaken
WMI or restore unsigned admission to migrate an old client.

Bounded checks: tests/test_shared_response_boundary.py,
tests/test_signed_bridge_client.py, tests/test_wealthmachine_http.py and
tests/test_kernel_contract_parity.py; real producer-consumer restart testing
lives in WMI tests/test_shared_consumer_integration.py. See
tests/evidence/shared-recovery and the Kernel SR-001 adoption handoff for pins,
commands, counts, warnings and dependency order. At the pinned Kernel 0.1.1
revision above, the four focused files pass 33 tests (0.28s); broad execution
remains blocked as described below. This is consumer regression evidence only.

The broad suite is **BLOCKED/INCOMPLETE**, not passing: two runs triggered the
environment's safety review over api.twitter.com access. A Python test-only
deny-egress guard was added, but the second attempt was also blocked; its
effectiveness is not established. No further broad rerun is justified here.
Use an independently isolated OS/container offline runner after inspecting the
network fixtures. Do not treat fallback dependencies, a monkeypatch or blocked
output as evidence of safe external operation. Docker image build/run remains
unverified separately. No default-branch repair follows from this draft.

Adoption order: Kernel boundary review, WMI #33 dependency, then the linked WMI
consumer and this producer as one compatibility gate. No merge is authorized.
Rollback before activation is to leave the existing branches untouched. A later
authorized sandbox rollback must stop writers, preserve history/head and all
obligations, and refuse unsupported history; never erase a state file or restore
permissive transport to make startup green. The September 5 two passes govern;
these are implementation checks, not a new architecture or third formal pass.

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
- Config snapshot: `curl http://localhost:5001/config`

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
- Update `ALLOWED_ORIGINS` and `ALLOWED_IPS` before exposing publicly.
- Rotate `ADMIN_TOKEN` and `JWT_SECRET` regularly in production.
- Every publish, identity change, lesson, and gate decision is recorded in a
  tamper-evident decision ledger (`data/decision_ledger.jsonl`). A broken
  chain or repeated job failures automatically disarm live posting. See
  [docs/SAFETY_AND_ROLLOUT.md](docs/SAFETY_AND_ROLLOUT.md) for the safety
  spine and the discipline for rolling out new platforms.
