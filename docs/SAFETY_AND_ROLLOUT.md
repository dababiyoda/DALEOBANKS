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
`breaker_tripped` / `breaker_reset` (heartbeat).

The app verifies the chain at startup (`app.py`); a broken chain disarms
live mode before anything can act.

### Kill switch
`KillSwitch` is the single authority over live posting. It wraps the existing
`config.LIVE` toggle, so disarming propagates instantly to the multiplexer
and every adapter through the config-update mechanism. `LIVE` defaults to
false; automatic transitions only ever *disarm*. Re-arming is a human
decision made through the dashboard toggle or `POST /api/toggle`.

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
