# Safety spine & multi-platform rollout discipline

This document describes the observability/safety layer added around the
agent's autonomy, and the discipline for extending the agent to new social
platforms. The guiding rule everywhere: **the system fails toward silence,
never toward runaway posting**, and every consequential event is recorded in
a tamper-evident ledger you can audit later.

## The safety spine

### Decision ledger (`services/ledger.py`)
An append-only, hash-chained JSONL log (default `data/decision_ledger.jsonl`,
override with `LEDGER_PATH`). Each entry carries the hash of its predecessor,
so history cannot be silently rewritten.

```python
from services.ledger import get_ledger

ledger = get_ledger()
ok, first_bad_seq = ledger.verify_chain()   # tamper check
ledger.replay("identity_change")            # the agent's identity history
ledger.replay("publish_attempt", limit=50)  # last 50 outbound attempts
```

Events currently chained: `startup`, `publish_attempt` / `publish_gated` /
`publish_result` (every platform write), `kill_switch`, `identity_change`,
`reflection_lesson`, `plan_start` / `plan_step` / `plan_critique` /
`plan_halt` / `plan_done` (reasoning traces), `cycle_error` /
`breaker_tripped` / `breaker_reset` (heartbeat), `armed` / `arm_refused`
(arming ceremony), `dm_received` (metadata only — never private text),
`revenue_event` / `link_click`, `discovery_proposal` /
`discovery_decision`, `okr_proposal` / `okr_decision`, `memory_consolidated` (dream
consolidation), `reception_prediction` / `prediction_accuracy` (self-calibrating simulator),
`admin_token_issued` (dashboard admin sessions),
`operator_prompted` / `operator_command` / `operator_sms_rejected` (operator
approval line), `instinct_verdict` / `identity_gate` (the reflex layer), and
`constitution_hash` / `constitution_tampered` / `constitution_missing`.

The app verifies the chain at startup (`app.py`); a broken chain disarms
live mode before anything can act.

### Kill switch and the arming ceremony
`KillSwitch` is the single authority over live posting. It wraps the existing
`config.LIVE` toggle, so disarming propagates instantly to the multiplexer
and every adapter through the config-update mechanism. `LIVE` defaults to
false; automatic transitions only ever *disarm*.

Arming is a ceremony, not a flag flip: `POST /api/toggle` with `live=true`
runs a preflight — ledger chain verification, heartbeat breaker state, and a
real X credential check (`get_me` API call) — and refuses with HTTP 409 and
the failed checks if any gate fails. Both outcomes are ledgered (`armed` /
`arm_refused`). Disarming is unconditional under every failure combination.
After a breaker trip, `POST /api/breaker/reset` (admin) clears the breaker
without re-arming.

### Constitution
`constitution.md` states the agent's fixed values. Its hash is recorded in
the ledger at startup and re-verified during the nightly cycle; runtime
drift records `constitution_tampered` and disarms live posting. The agent
can propose changes to its goals — never to its constitution; amendments
happen only through a human commit and restart.

### Human gates on self-modification
The mind widens itself only through gates a human holds:

- **Discovery**: a daily job proposes new voices (accounts with repeated
  genuine engagement) and keywords (topics that repeatedly earn high
  J-scores). Proposals are ledgered and pending until decided via
  `POST /api/discoveries/{id}/decision`; only approvals reach perception.
- **Goals**: the planner files OKR adjustments as ledgered `GoalProposal`s.
  The active OKR is the latest human-approved proposal (else the default),
  decided via `POST /api/goals/proposals/{id}/decision`.

### Operator approval line (`services/operator_line.py`)
When the agent needs judgment rather than rules, it files an
`ApprovalRequest` and prompts the operator — by SMS when Twilio is
configured (`TWILIO_ACCOUNT_SID` / `TWILIO_AUTH_TOKEN` / `TWILIO_FROM` /
`OPERATOR_PHONE`), and always in the dashboard inbox
(`GET /api/operator/requests`). Commands run through one parser whether they
arrive as a signed Twilio webhook (`POST /api/operator/sms`, signature- and
sender-validated before anything is parsed) or from the dashboard
(`POST /api/operator/command`, admin JWT):

`YES <code>`, `NO [code]`, `EDIT [code] <text>`, `WHY [code]`,
`HOLD [code]`, `FREEZE`, `NEWS`, `INTERVIEW`, `OPINION: <thought>`

Three rules are load-bearing: **YES requires the request's 4-character
approval code** (e.g. `YES A7K2`) unless exactly one P1 request is pending —
a bare YES is rejected whenever it could be ambiguous, so the wrong action
can never be approved by accident, and approval never enables standing
autonomy; **FREEZE disarms outbound action immediately** through the kill
switch; **OPINION becomes a `SelfSignal`** — a signal the agent weighs,
never automatic doctrine. Every prompt and command is ledgered
(`operator_prompted` / `operator_command`), and rejected webhook calls
(bad signature or unknown sender) are ledgered as `operator_sms_rejected`.
`operator_line.py` is the public facade; SMS transport and signature
validation live in `services/operator_notifications.py`.

### Instinct Engine and Identity Gate (`services/instinct.py`)
A deterministic reflex layer that runs on every posting path, before and
after generation:

- **Instinct Engine** (pre-generation) scores each opportunity — identity
  fit, mission fit, business leverage, relationship value, credibility risk,
  ragebait risk, evidence need — and returns one of `engage`, `ignore`,
  `save_for_later`, `research_first`, `human_review`, `block`, `dm_instead`,
  `create_asset`. Ragebait and insults are blocked before a single token is
  generated; hostile relationships get de-escalated privately instead of
  publicly; high-stakes opportunities file an operator approval request.
- **Identity Gate** (post-generation) scores the draft — belief fit, voice
  fit, mission fit, credibility risk, drift risk — and returns `allow`,
  `rewrite` (one regeneration attempt), `block`, or `needs_human` (files an
  `ApprovalRequest`). Drafts with unsourced strong claims stop here.

Both layers only narrow what the existing gates may see; they never publish.
Every verdict is ledgered (`instinct_verdict` / `identity_gate`).

### Prompt injection defense (`services/prompt_firewall.py`)
Everything the agent reads from outside — mentions, DMs, timeline posts,
trends, and its retrieved memories of them — can inform the agent but never
command it. The firewall is where that constitution invariant becomes code:

- **Sanitizer**: strips invisible/bidi control characters and neutralizes
  role-play markers (`system:` at line start) in all inbound text.
- **Scanner**: scores instruction-shaped content ("ignore previous
  instructions", "reveal your prompt", ...); instinct blocks any opportunity
  scoring ≥ 0.4, and DMs at that level are quarantined as `dm_flagged`
  (`injection_suspect`) — they never become reply candidates.
- **Fencing**: external text enters prompts only inside `[UNTRUSTED DATA]`
  delimiters (collision-escaped, so content cannot close its own fence) —
  applied to reply/quote originals and world-model context.
- **Canary + output guard**: every system prompt carries a per-process
  canary token; any draft that leaks it, echoes the untrusted fences, or
  contains invisible characters is dropped before validation.
- **Memory safety**: `is_doctrine_safe` keeps instruction-shaped text out of
  lessons and self-signals; world-model observations are sanitized and
  tagged with their injection risk.

### Raw vault vs sanitized context (`services/raw_vault.py`)
The sanitizer never destroys the source record. Raw external content is
preserved verbatim in an append-only vault (`data/raw_vault.jsonl`,
`RAW_VAULT_PATH`) with provenance for audit and replay; each ContextPacket
carries its `vault_id`. Only sanitized, delimited, evidence-only context may
enter prompts.

### ContextPackets (`services/context_packet.py`)
Every sensor distills what it sees into one structured shape before it can
influence anything: sanitized text plus extracted claims, stakes,
incentives, human cost, system failure, evidence needs, injection risk, and
provenance. Mentions, DMs, timeline posts, trends, and operator self-signals
all speak this language; the Instinct Engine consumes packets directly. Raw
prompt sludge never travels between services.

### Inbound senses
The `dm_ingest` job reads incoming DMs (read-only, safe in any LIVE state).
Inbound text is untrusted input: it passes the EthicsGuard before it can
influence anything (harmful messages are stored as `dm_flagged` and never
become reply candidates), and the ledger records metadata only — private
message text never enters the tamper-evident log. The value-DM job answers
unanswered inbound DMs before doing any cold outreach.

### Publish gate (`services/social_base.py`)
`BaseSocialClient.publish` is a template method. Before any adapter's
`_publish_impl` runs, the gate:

1. records a `publish_attempt` in the ledger,
2. forces a dry run if the kill switch is disarmed,
3. forces a dry run (and records `publish_gated`) if the platform exceeds
   the rate governor's cap (default 30 live actions/hour per platform,
   override with `RATE_GOVERNOR_MAX_PER_HOUR`),
4. records the `publish_result`.

Safety is inherited, never re-implemented: any new platform adapter gets all
of this by subclassing.

### Heartbeat (`services/heartbeat.py`)
All scheduled jobs register through `heartbeat.supervise(name, fn)`. A
failure in one job never kills the loop; every error is ledgered; three
consecutive failures trip a breaker that disarms live posting.
`reset_breaker()` clears the breaker but deliberately does not re-arm.

### Thought DSL (`services/thought_dsl.py`)
Outbound proposals run through `ThoughtInterpreter` before publishing: the
plan and every step land in the ledger, and ACT steps must clear the
`EthicsGuard` (mandatory) and the `Critic` (blocking issues halt the plan).
When the agent does something surprising, `ledger.replay("plan_step")` shows
the reasoning chain and the exact gate decision behind it.

### Semantic memory (`services/semantic_index.py`)
Lessons are indexed into a durable associative store (default
`data/semantic_index.jsonl`, override with `SEMANTIC_INDEX_PATH`) that
survives restarts and database note pruning, and feeds topic-relevant
lessons back into generation.

### Curiosity drive (`services/optimizer.py`)
`novelty_bonus` gives under-explored bandit arms a bounded lift
(`weight / sqrt(1 + pulls)`, capped at 0.15) so the agent keeps exploring
instead of ossifying — without ever overriding a clearly better posterior
or any safety gate.

## Adding a new platform

The architecture is already multi-platform (`SocialMultiplexer` routes to
adapters). Adding a platform is a rollout discipline, not new architecture:

1. **One new client.** Create `services/<platform>_client.py` subclassing
   `BaseSocialClient` and implementing `_publish_impl` (never override
   `publish` — that would bypass the gate). See `mastodon_client.py` for the
   minimal shape.
2. **Register it** in `SocialMultiplexer.__init__` behind an
   `ENABLE_<PLATFORM>` config flag, and give it a weight in
   `PLATFORM_WEIGHTS`.
3. **Ship in shadow mode.** New platforms start with `live=False` and the
   flag disabled in production. Run a fixed observation window (a week is a
   good default) during which the adapter only dry-runs.
4. **Read the ledger before arming.** During the window, review
   `ledger.replay("publish_attempt")` and `replay("publish_gated")` for the
   platform: volume, timing, content kinds. Only then enable live mode.
5. **Per-platform tone.** Add a persona/tone profile for the platform before
   arming; the same message rarely fits X and LinkedIn.

The kill switch, rate governor, ledger, and heartbeat apply to the new
platform automatically — widening the agent's body can never outrun the
safety layer.

## What stays a human decision

- Re-arming live mode after any automatic disarm (breaker, broken chain).
- Enabling a new platform's live mode after its shadow window.
- Any future agent-to-agent messaging: inbound content must remain data,
  never instructions, and must pass the same guards as everything else.
  Keep a permanent human checkpoint on this one.
