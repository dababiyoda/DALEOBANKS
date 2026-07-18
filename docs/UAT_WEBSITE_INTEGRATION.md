# DALEOBANKS -> UAT website integration contract

## Current decision

DALEOBANKS is a separate sibling service. The ChatGPT Site must not embed it,
receive its production secret, or treat a connection request as a live runtime
connection. The existing versioned exchange remains server-to-server and held
for human review:

`DALEOBANKS OpportunityPacket -> UAT VentureAssessment -> DALEOBANKS drafts and approval request`

Both repositories implement the schema-1.0 compatibility shape. That proves a
contract, not delivery, authorization, payment, venture creation, or external
execution.

## Authority boundary

- DALEOBANKS discovers or receives an opportunity and records it locally.
- An administrator approves the packet before transmission.
- UAT validates and records the packet, then returns a held assessment.
- DALEOBANKS forces `requires_human_approval=true` and creates reviewable drafts.
- Neither service may translate an assessment into publishing, spending,
  contracting, deployment, or venture launch without a separate governed
  action and designated human approval.
- The website may record an activation **request** and display status. It may
  not store the service credential or call either service directly.

## LIVE PLAYER separation

LIVE PLAYER is UAT agent context, not a DALEOBANKS integration. It must remain
outside this protocol unless a future, separately approved data-flow contract
defines an exact context version, purpose, fields, retention rule, and redaction
policy. Context can influence a bounded recommendation; it cannot grant a tool,
role, credential, budget, or execution authority.

## Current transport

DALEOBANKS supports `mock` and `http` modes. HTTP sends a schema-1.0 packet to
`{WEALTHMACHINE_URL}/api/opportunities/intake` with the optional
`WEALTHMACHINE_INTAKE_TOKEN`. UAT fails closed in production if its matching
intake token is absent. This static-token compatibility mode is suitable for a
bounded sandbox only; production acceptance requires scoped, rotated or
short-lived workload credentials.

## Production activation gates

1. Name service owners and approve exact sandbox and production endpoints.
2. Enforce authenticated administration on every DALEOBANKS mutation and
   authenticated access to private operator data.
3. Replace placeholder secrets and wildcard origins; bind JWT issuer and
   audience.
4. Add a durable outbox/inbox with message ID, idempotency key, attempt,
   timestamp, contract version, payload hash, receipt, and terminal state.
5. Test duplicate, delayed, reordered, replayed, malformed, expired, and
   partially processed messages.
6. Reconcile each transmission and assessment against both authoritative
   stores; never infer completion from an HTTP request alone.
7. Add rate limits, circuit breaking, schema-drift holds, kill switches, and
   incident ownership.
8. Prove that approval cannot be self-issued by the proposing service or agent.
9. Complete security, privacy, legal, and recovery review.

Until every gate is evidenced, `runtime_status=not_configured` and
`execution_authority=none` are mandatory customer-facing labels.
