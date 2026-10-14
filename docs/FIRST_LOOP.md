# FIRST_LOOP — The First Business Loop and Its Side-Effect Inventory

Status: **DECLARED — NOT AUTHORIZED. NOTHING EXTERNAL RUNS WITHOUT ALFONSO'S EXPLICIT YES.**

This document names the single business loop DALEOBANKS is working toward and
lists every external side effect that loop requires. Until each side effect is
either mediated by the kernel or explicitly marked human-only, the loop stays
in shadow.

It is subordinate to the Kernel. Venture gates are owned by
`uniimente-kernel/workflows/venture-validation.yaml`. Consequence authority
is owned by the Kernel Gate. The SR-001 boundary in `README.md` still holds:
no live X operation, deployment, credential use or economic outcome is
authorized or claimed here. CMC and VDM remain zero.

Freeze rule: no new agents, dashboards, media properties, autonomy levels or
business categories unless they help complete *this* loop.

---

## 1. The canonical integration target

**One loop, chosen and frozen: the Diaspora FIRE Starter Kit.**

| Field | Value |
| --- | --- |
| Offer | A written educational starter kit covering how to calculate your number, how to build a first reserve, and how to read the systems that profit from dependency |
| Buyer | An individual saver who pays for themselves. No employer, institution or procurement process is involved |
| Beneficiary | The buyer. Because buyer and beneficiary are the same person, delivery can be verified directly |
| Price | About $19, one-time. This is a hypothesis, not a commitment; willingness to pay is what the loop tests |
| Delivery | **Manual.** A human writes the kit and a human sends it. No fulfilment automation exists or is planned for the first loop |
| Governing transaction | One payment, one delivery, one confirmation of receipt |
| Regulatory surface | Educational content only. No personalized financial advice, securities, managed money, health data or regulated profession |
| Kill conditions | Zero paid conversions in the validation window; any complaint of misleading claims; any platform warning; the operator's judgment |
| Automated spend ceiling | $0. Any expenditure is a human action outside the machine |

**Why this loop.** It is the smallest offer that can reach Kernel venture gate
`5_first_paid_pilot` ("money moved; not enthusiasm"), which is payment-tier
evidence, the top of DALEOBANKS's evidence hierarchy. It does so while touching
the fewest regulated surfaces and needing no delivery infrastructure.

**What this loop is not.** It is not a healthcare, transportation, benefits,
credentialing or procurement product. DALEOBANKS is a public intelligence, media
and demand-sensing organ, and concepts from unrelated ventures do not enter here.

---

## 2. Side-effect inventory

"Mediated" means the act runs through a `CapabilityGrant` minted from a human
`ApprovalRequest`. The grant may only narrow the approval's declared scope
(`services/capability.py`). It is validated at execution time and recorded in
the decision ledger. "Human-only" means no machine path exists and none will be
built for the first loop.

| # | External action | Adapter | Credential | Risk | Approval | Receipt | Rollback | Reconciliation |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | Publish one educational post | `services/x_client.py` (dry-run while `LIVE` is false; SR-001 authorizes no live X operation) | X account. **Does not exist yet** | Reputation; platform policy | `CapabilityGrant` from an approved `publish` request: one draft, one lane, one use, 72h | Platform post id and URL | Delete the post. The ledger entry stays | Post id recorded against the grant. No id means the act did not happen |
| 2 | Stand up a landing page | None. No deploy adapter exists | Hosting account. **Does not exist yet** | Claim accuracy; disclosure | **Human-only** for the first loop | Deployed URL | Take the page down | Compare the live text with the approved draft |
| 3 | Take payment | None. No payment adapter exists, by design | Payment processor account. **Does not exist yet** | Financial; chargeback; tax | **Human-only. Never mediated in the first loop** | Processor transaction id | Refund (by a human) | The transaction id becomes a `raw_evidence_refs` entry on a payment-tier `ValidationResult` |
| 4 | Deliver the kit | None. Manual email | Email account. **Does not exist yet** | Delivery failure; wrong recipient | **Human-only** | Sent-message id | Resend; refund if undeliverable | Classify the result `success` only after the buyer confirms receipt |
| 5 | Reply to a buyer question | `services/x_client.py` or email (dry-run) | Same as rows 1 and 4 | Advice boundary: replies must stay educational | One `CapabilityGrant` per reply, or human-only if the question touches the buyer's personal circumstances | Message id | Send a correcting follow-up | Compare the reply text with the approved draft |

**Coverage for this loop:**

- **Executed:** 0 of 5.
- **Mediated by design:** 2 of 5 (rows 1 and 5).
- **Mediated in code on `main`: 0 of 5.** Verified 2026-10-14: `services/x_client.py`
  `create_tweet` and `send_dm` do not consult a `CapabilityGrant`; only `LIVE=false`
  stops them. The enforcement already exists as an unmerged stack that routes every
  X write family through the Kernel Consequence Gate (DALEOBANKS #58 → #59 → #60 →
  #61 → #73, which depends on Kernel #11 → #25). Merging or superseding that stack is a
  founder decision. Until then `LIVE` must stay false, and arming it would bypass
  rows 1 and 5.
- **Deliberately human-only:** 3 of 5 (rows 2, 3 and 4).

Coverage is not a number to push up by building adapters. Payment and delivery
are human-only on purpose, and that is the correct end state for the first loop.

Verified on 2026-10-14: the repository has no payment, deploy or fulfilment
module. `stripe` appears only as a conversion-source label in
`tests/test_revenue.py`.

### The bypass rule

Any way to perform one of these five actions without passing through the kernel
is a defect, not a shortcut. No credentials for any of them exist in the
environment.

---

## 3. What the shadow loop proves

`tests/test_shadow_loop.py` drives the entire chain with the external act mocked
out:

1. Signal
2. OpportunityPacket
3. Adversarial VentureAssessment
4. Drafts and an ApprovalRequest
5. Human YES
6. A CapabilityGrant narrower than the approval
7. One validated consumption of the grant
8. A shadow execution record
9. A shadow ValidationResult
10. A reconstructed DecisionEpisode

The test also asserts the failure modes:

- A spent grant cannot be replayed.
- A grant cannot name a resource the human never approved.
- The ledger chain stays intact.
- Closing a loop never flips `LIVE`.

**What it does not prove: that anyone wants the kit.** A shadow result carries
`metadata.mode == "shadow"`. It is therefore excluded from:

- the anti-cathedral evidence window
- the evidence multiplier
- external totals
- the loop closure rate

Episodes report `externally_closed` and `shadow_only` separately from
`loop_closed`. A rehearsal cannot unblock internal expansion or inflate a
metric. No external ValidationResult exists yet.

---

## 4. The human-authorization boundary

The machine stops here. These decisions belong to Alfonso and cannot be
delegated:

1. **Designate or create the X account** the main lane speaks from. This
   requires the SR-001 boundary to be lifted for that one lane.
2. **Approve EXPERIMENT-001**, the single educational post specified in
   `docs/EXPERIMENT_001.md`.
3. **Decide whether to run the paid pilot.** If it goes ahead, the landing
   page, payment and delivery steps (rows 2–4) are performed by a human.

Nothing in this repository arms itself.
