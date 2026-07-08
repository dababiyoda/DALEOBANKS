# Idea Refinery & Venture Cockpit — Architecture Improvement Memo

The governed idea refinery: raw operator thoughts, public signals, and
audience reactions become media drafts, opportunity packets, and venture
assessments. **The machine prepares. The human authorizes. The world
responds. The system learns.**

## 1. What already exists (and was reused, not rebuilt)

| Need | Existing capability reused |
|---|---|
| Approval workflow | `ApprovalRequest` + operator line (SMS/dashboard, YES-with-code) |
| Audit trail | Hash-chained `DecisionLedger` — all refinery events chained |
| Injection defense | `prompt_firewall` sanitizes/flags intake and inbound wire data |
| Raw preservation | `raw_vault` (sensors) — idea intake stores sanitized text, ledgered |
| Content safety | EthicsGuard/Critic/Identity Gate on any actual publish path |
| Publish gating | `BaseSocialClient` gate + kill switch + rate governor — untouched |
| Memory | Semantic index / world model / evidence library / relationships |
| LLM access | `LLMAdapter` with offline template fallback |

## 2. What was deliberately NOT rebuilt
- No second approval system: venture actions file into the same operator queue.
- No new publish path: an approved `MediaAssetDraft` is *publishable*, but
  publishing still runs through the existing gated pipelines (LIVE, kill
  switch, identity gate, thought DSL). Nothing in the refinery posts.
- No merged monolith: WealthMachineIntelligence stays a separate system
  behind a wire protocol.

## 3. Safest integration points (chosen)
- **`services/venture_protocol.py`** is the single contract file — designed
  to be copied verbatim into WealthMachineIntelligence (schema version 1.0,
  enums, wire converters, validation). Inbound assessments are validated as
  untrusted input (`validate_assessment_wire`).
- **`WealthMachineClient`**: `mock` mode (deterministic local scorer, the
  default with no credentials) and `http` mode behind `WEALTHMACHINE_URL` /
  `WEALTHMACHINE_MODE`. Push intake also exists:
  `POST /api/wealthmachine/assessments/receive` (admin/service JWT).

## 4. What was added
- Models (repo dataclass style): `Idea`, `OpportunityPacket`,
  `VentureAssessment`, `ValidationResult`, `MediaAssetDraft`, `AccountLane`.
- `services/idea_refinery.py`: intake → thesis → audience options →
  localized drafts (incl. Ghanaian-immigrant FIRE education, Spanish, video
  script) → OpportunityPacket. Offline-deterministic templates; LLM polish
  optional later.
- `services/wealthmachine_client.py`: evaluate (mock/http) +
  `assessment_to_actions` (validation plan, landing-page copy, buyer
  interview script, outreach draft, ApprovalRequest).
- Endpoints: `/api/ideas/intake`, `/api/ideas`, `/api/ideas/{id}/refine`,
  `/api/opportunities` (+ `/decision`, `/send-to-wealthmachine`),
  `/api/wealthmachine/assessments/receive`, `/api/media/drafts`
  (+ `/decision`), `/api/lanes` (GET/POST).

## 5. Simplified for the first implementation
- Draft generation is deterministic templates first (testable, offline);
  LLM polish is an additive upgrade, not a dependency.
- Dashboard views (Idea Inbox, Opportunity Inbox, Assessments, Drafts,
  Lanes) are **TODO Phase 5** — the JSON endpoints are dashboard-ready.
- Full LLM harness (PromptRegistry/ModelRouter/JudgePipeline) is **TODO
  Phase 6**; today's guardrails (firewall canary, output guard, identity
  gate, finance guard) already cover the enforcement core.

## 6. Hardcoded legal/safety guardrails (not configurable)
- `LANE_POLICY` in `venture_protocol.py`: no fake consensus, no coordinated
  inauthentic amplification, no auto-DMs at scale, no impersonation, no
  undisclosed sponsorships, no stolen media, no guaranteed financial
  claims, no personalized legal/financial advice without qualified review.
- `validate_identity_type` rejects `fake_person`, `impersonation`,
  `fake_expert_identity`, `ban_evasion_account`,
  `engagement_manipulation_account` with a `ValueError`/HTTP 422.
- Finance guard (`check_educational`): personalized-advice and
  income-promise phrasing fails a draft; finance drafts carry
  "Educational only — not financial advice."
- `VentureAssessment.requires_human_approval` is forced `True` on this side
  regardless of what the wire says.

## 7. Open-source/local-first
Python/FastAPI/APScheduler/React already; the refinery adds zero paid
dependencies. Twilio, X API, OpenAI, and WealthMachine HTTP are all
optional behind env config; everything runs in mock/local mode.

## 8. Optional/mock-only until credentials exist
- WealthMachine HTTP (`WEALTHMACHINE_URL`), SMS (`TWILIO_*`),
  LLM polish (`OPENAI_API_KEY`), payments (`/api/conversions` webhook).

## 9. What made this stronger than the original prompt
- Inbound assessments are treated as **untrusted wire data** (validated,
  approval forced) — the venture engine can inform, never command.
- One approval queue, one ledger, one firewall for both minds' traffic.
- Deterministic mock scorer means go/defer/kill behavior is test-pinned
  before the real engine is attached.

## 10. Remaining plan
- **WealthMachineIntelligence repo** (out of this session's GitHub scope —
  needs a session scoped to it): copy `venture_protocol.py`, add
  `POST /api/opportunities/intake` mapping packets into the existing
  venture loop, return the wire assessment.
- Phase 5 dashboard views; Phase 6 LLM harness; ValidationResult ingestion
  UI once real validation runs happen.

## The wire contract (v1.0)
`OpportunityPacket` → see `services/venture_protocol.py::packet_to_wire`
(JSON: all dataclass fields + `schema_version`, ISO `created_at`).
`VentureAssessment` ← must pass `validate_assessment_wire`: `go_no_go` ∈
{go, defer, kill, needs_more_evidence}, `opportunity_packet_id` required,
`opportunity_score` ∈ [0,1].
