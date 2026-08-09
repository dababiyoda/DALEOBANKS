# Operating Authority

Every claim here is labeled `IMPLEMENTED`, `PROPOSED`, or `ASPIRATIONAL`. A
document describing a capability is not the capability.

The distinction this file exists to hold: **current authority** is what the
system may do today. **Intended authority** is what a future standing mandate
should permit. Implementation existing is not authority existing. Nothing
below grants anything.

## Current authority

| Action | State | Gate |
| --- | --- | --- |
| Read sources, extract claims, draft content | `IMPLEMENTED` | none beyond evidence checks |
| Localize, run structural parity checks | `IMPLEMENTED` | claim/source identity must match |
| Shadow publication (`live=false` adapters) | `IMPLEMENTED` | registered SHADOW account + adapter refuses live |
| Live publication | **NOT AUTHORIZED** | no declared account, no standing mandate |
| Direct messages, sensitive outreach | **NOT AUTHORIZED** | unchanged from historical posture |
| Money movement, spending | **NOT AUTHORIZED** | no budget envelope exists |
| Deployment | **NOT AUTHORIZED** | — |
| Cross-repository effects | **NOT AUTHORIZED** | scope is this repository |

No account is registered. No credential is referenced. No handle may be
inferred from public search — the registry takes declarations, never guesses.

## The four risk tiers

**Tier 1 — routine.** Source monitoring, drafting, translation, repurposing,
analytics, content tagging. May eventually run under standing authority.
Today they run and stop at draft.

**Tier 2 — organ decisions.** Campaign adjustment, vendor change inside
budget, a new routine content experiment, pricing experiments, ordinary
sponsorship evaluation. Requires DALEOBANKS policy approval within charter.

**Tier 3 — internal exceptions.** Significant reputational risk, large budget
deviation, controversial public issue, material policy conflict, security
incident. Escalates above the organ.

**Tier 4 — founder-reserved.** Core brand mission, acquisitions, new
regulated industry, large capital commitments, ownership or control changes,
new constitutional authority, extraordinary legal exposure, major new
external permissions. `IMPLEMENTED`: tier4 content stops before editorial
review rather than being approvable locally.

## Where authority actually comes from

Organ-local policy may tighten. It may never loosen. Nothing in this
repository is a root constitution.

```
Kernel authorization certificate     may this organ act at all?
        ↓
organ-local policy                   should it, and is it ready?
  account prerequisite
  editorial review
  CapabilityGrant
  KillSwitch, rate governor
        ↓
adapter
```

Organ-local refusal runs *after* Kernel authorization on purpose. A
certificate permits; it never compels. Either layer may say no.

`PROPOSED` — the Kernel side (PR #66) imports its aperture from a sibling
checkout and skips its tests when absent. Not deployable until the Kernel
ships an installable client.

An `AccountLane` status, an editorial approval, and a passing test are all
prerequisites. None of them is authority.

## Escalate when

Claim confidence is insufficient · content is high-risk · a budget limit
would be exceeded · new platform access or credential is required ·
sponsorship disclosure is unclear · legal exposure changes · a controversy
exceeds policy · a security incident occurs · an automated action conflicts
with policy · someone asks for individualized professional advice.

## Failure posture

Degrade toward pause, then draft-only, then read-only. Escalate. Preserve
evidence.

Never degrade toward uncontrolled publishing or spending. A broken ledger
chain, crisis state, tripped kill switch, exhausted grant, or stale scope
fails toward silence.

## What would change this file

Six declarations, and none of them are code: surface, timezone, source
packet, owned-audience destination, resource ceiling, stop condition. The
aspiration registry refuses to predeclare a campaign without the last two and
names them when it refuses.
