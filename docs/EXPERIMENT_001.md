# EXPERIMENT-001 — First Bounded External Experiment

Status: **PREPARED — NOT AUTHORIZED. NOTHING PUBLISHES WITHOUT ALFONSO'S EXPLICIT YES.**

This document is the complete, pre-registered specification for the
institution's first contact with external reality. Thresholds are written
*before* launch; post-hoc reinterpretation creates new records, never
edits to this file.

## Hypothesis

A culturally aware, educational financial-independence post in the
DaLeoBanks voice produces substantive engagement (replies that engage the
mechanism, saves, profile follows from relevant accounts) from an audience
interested in systems thinking and financial independence — demonstrating
that the doctrine translates into public value, not just internal drafts.

## Intervention (the exact asset)

One post, one lane, one time. Draft (persona: Challenge → Analyze →
Propose → Inspire; educational only):

> Financial independence is not selfish.
>
> It is protection from systems that profit from your dependency —
> systems designed so that missing one paycheck becomes a crisis.
>
> The mechanism is simple: every month of expenses you hold in reserve
> buys you the power to say no. No to exploitative terms. No to
> emergencies becoming debt spirals.
>
> Start by knowing your number: what one month of your life actually
> costs. Most people have never calculated it.
>
> What stopped you the first time you tried to build a reserve?
>
> (Educational only — not financial advice.)

Disclosure included. No product, no link, no offer, no DM solicitation.

## Design

| Field | Value |
|---|---|
| Account lane | DaLeoBanks flagship (X) — **prerequisite: Alfonso designates/creates the account** |
| Target audience | English-speaking followers/browsers interested in systems + FIRE |
| Baseline | None exists (first post); this run *establishes* the baseline |
| Observation window | 7 days from publication |
| Success threshold | ≥3 substantive replies (engaging the mechanism, not emoji) OR ≥10 saves/bookmarks |
| Failure threshold | 0 substantive replies AND <3 total interactions |
| Cost ceiling | $0 (organic post only) |
| Founder attention budget | ≤30 min total (approve, glance daily, record result) |
| Confounders | zero-follower cold start; posting time; algorithm variance; single-post sample |
| Stop conditions | any platform policy notice; any harassment pile-on; crisis pause; Alfonso says stop |
| Rollback | delete the post; ledger the deletion; record outcome as `inconclusive` with rollback note |
| Next-decision rule | success → draft Ghanaian-diaspora localization as EXPERIMENT-002; failure → revise hook, one retry as 002; either way, record the ValidationResult first |

## CapabilityGrant draft (minted only after YES)

```json
{
  "action_type": "publish_post",
  "exact_action": "Publish the EXPERIMENT-001 draft, verbatim as approved",
  "resource": "<media_draft_id>",
  "account_lane_id": "<flagship_lane_id>",
  "max_cost": 0.0,
  "maximum_uses": 1,
  "ttl_hours": 72,
  "rollback_note": "Delete post; ledger deletion; record inconclusive result"
}
```

## ValidationResult template (filed at window close — zero response included)

```json
{
  "opportunity_packet_id": "<fire_packet_id>",
  "experiment_ref": "EXPERIMENT-001",
  "capability_grant_id": "<grant_id>",
  "validation_type": "content_probe",
  "hypothesis": "(as above)",
  "intervention": "(exact post text)",
  "observation_window_start": "<publish_ts>",
  "observation_window_end": "<publish_ts + 7d>",
  "success_threshold": ">=3 substantive replies OR >=10 saves",
  "failure_threshold": "0 substantive replies AND <3 interactions",
  "measured_outcomes": {"substantive_replies": 0, "saves": 0, "follows": 0, "objections": []},
  "evidence_tier": "engagement",
  "result_classification": "<success|failure|mixed|inconclusive|negative>",
  "causal_note": "single post, cold start — treat as baseline, not causation",
  "next_decision": "<per the next-decision rule>"
}
```

## Execution path (Stage 7, after authorization only)

1. Alfonso approves via the approval queue (`YES <code>`).
2. A CapabilityGrant is minted from that approval (one post, one lane, one use, 72h expiry).
3. `validate_and_consume` gates the publish — ledger intact, no crisis pause, exact draft, exact lane.
4. The approved text publishes **verbatim** (manually by Alfonso, or via the gated pipeline once the lane is armed).
5. Outcomes are recorded through `POST /api/validation-results`; the DecisionEpisode closes.
6. Zero response is a completed **negative** ValidationResult — recorded, never erased.
