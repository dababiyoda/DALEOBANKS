# DaLeoBanks - Autonomous AI Agent

DaLeoBanks is a production-grade, self-evolving AI agent that operates on Twitter/X. The stack pairs a Python FastAPI backend (agent logic, scheduler, persona management) with a Node/Express + Vite frontend that proxies requests to the backend.

## Run it

```bash
python -m daleobanks run          # works with no config: runs the canon
python -m daleobanks canon        # what the defaults actually contain

cp founder_declaration.example.yaml founder_declaration.yaml
# fill in the six campaign fields, the owned destination, and your surfaces

python -m daleobanks validate    # names every decision you have not made
python -m daleobanks preflight   # what is authorized, what is blocked
python -m daleobanks run         # one full cycle, shadow only
python -m daleobanks report      # the status report, computed from the store
```

With no declaration file at all it runs anyway, on the mandate's own canon:
the UNIIMENTE flagship channel and its topic mix, the three community
pillars, the four-stop rabbit hole with an opposing case and an off-ramp at
every stop, the 8:00 PM daily edition's seven sections, and five candidate
shared primitives. What canon cannot supply is what canon cannot know — the
handle, the destination, the budget, the source packet — so it seeds the
structure, refuses the rest, and names the four.

The public UNIIMENTE channel is a media surface beneath DALEOBANKS. It is not
the Golden Kernel and carries no constitutional authority; the canon record
says so in a field, because that is the most expensive confusion available.

`validate` refuses an incomplete declaration and names the missing field,
because a default is a decision nobody made. `run` goes source → claim →
content → localization → shadow receipt → campaign predeclaration → next
move, and stops at whatever the declaration does not support rather than
inventing it.

Two things the declaration cannot do. It cannot raise authority: every
surface is seeded `SHADOW` with `SHADOW_ONLY` authorization, and live
publication still needs the separate approval and capability path. And it
cannot flatter the report — `report` is computed from the durable store, so
it will tell you a full cycle ran and that nothing went live, in the same
breath, because both are true.

## Canonical product direction

The current X agent is only the first operating surface of the larger DALEOBANKS product.

DALEOBANKS is being developed toward a **global lifestyle brand, multilingual media network, community and commerce system, early cash engine for UNIIMENTE, opportunity-sensing organ, distribution network, collaboration platform, and long-horizon civilization-seeding institution**.

Its permanent mission is the **Infinite Goal Chase**: help reduce the distance and time between Alfonso Lopez's active lawful aspirations and verified reality, then use achieved capability as substrate for harder aspirations. For material aspiration planning, use the Backcast-GPS-based aspiration acceleration protocol and prioritize shared primitives, real evidence, ethical influence, collaboration, distributed capability, and durable progress over vanity activity.

The current runtime does **not** prove that all of those future capabilities already exist.

Read these documents before making material changes to DALEOBANKS identity, product direction, media architecture, multilingual expansion, monetization, community strategy, aspiration planning, influence campaigns, autonomy, Venture Cell routing, or relationship to UNIIMENTE:

- [Canonical DALEOBANKS Lifestyle Brand, Media Network, and Civilization-Seeding Architecture](docs/DALEOBANKS_MEDIA_BRAND_ARCHITECTURE.md)
- [DALEOBANKS Infinite Goal Chase](docs/DALEOBANKS_INFINITE_GOAL_CHASE.md)
- [DALEOBANKS Infinite Aspiration Chase and Acceleration Protocol](docs/DALEOBANKS_ASPIRATION_ACCELERATION_PROTOCOL.md)
- [DALEOBANKS Founder Intent Lineage](docs/DALEOBANKS_FOUNDER_INTENT_LINEAGE.md)
- [Safety and Rollout](docs/SAFETY_AND_ROLLOUT.md)
- [Idea Refinery and Venture Cockpit](docs/IDEA_REFINERY.md)
- [Constitution](constitution.md)

The architecture docs preserve the intended destination. The code and tests remain the source of truth for what the current runtime demonstrably does.

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
