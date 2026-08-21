# DALEOBANKS Architecture Ownership

## Decision scope

- Decision ID: `DB-DEC-001`
- Founder intent: `DB-FI-001` through `DB-FI-015`
- Deliberation level: Standard
- Authorized decision owner: Alfonso Lopez
- Repository inspected: `dababiyoda/DALEOBANKS`
- Repositories intentionally not modified: UNIIMENTE/Golden Kernel, WealthMachineIntelligence, PumpStation, and every other repository
- Effective trigger: merge of the Phase 0 implementation after founder review; the draft PR itself grants no production authority

## System role map

| System | Unique responsibility | Canonically owns here | Consumes | Must not own | Lifecycle |
| --- | --- | --- | --- | --- | --- |
| DALEOBANKS | Public identity, sensing, media, relationships, distribution, community/commerce signals, opportunity production | Account Registry; persona; source/claim/content/localization/receipt state; IdeaRefinery; organ analytics | Founder mission and authority; source evidence; platform APIs; WMI assessments | Root Constitution, unrestricted treasury, WMI strategy implementation, PumpStation settlement | active |
| UNIIMENTE / Golden Kernel | Constitutional identity, authority, standing mandates, consequence controls | External boundary; no implementation copied here | DALEOBANKS proposals and evidence | DALEOBANKS specialist media state | unavailable to this repository |
| WealthMachineIntelligence | Strategic and commercial assessment | `VentureAssessment` producer behind the wire boundary | Canonical `OpportunityPacket` | DALEOBANKS public identity, media, or account state | external boundary |
| PumpStation | Eligibility, proof, settlement, reputation, and ownership pathways | External venture-cell state | Consent-bearing qualified handoffs | DALEOBANKS audience or media authority | external boundary |

## Canonical contract map

| Concept | Canonical owner | Source | Consumers | Version rule | Parity evidence |
| --- | --- | --- | --- | --- | --- |
| DALEOBANKS account record | DALEOBANKS | `db.models.AccountLane` through `services.account_registry.AccountRegistry` | API, media loop, future adapters | Additive backward-compatible fields until a schema migration is authorized | `tests/test_account_registry.py` |
| DALEOBANKS media knowledge record | DALEOBANKS | `SourceRecord`, `ClaimRecord`, `ContentRecord`, `LocalizedArtifact` | Media loop and API | Material facts are claim/source identities; localization cannot change the set | `tests/test_media_operating_system.py` |
| Publication receipt | DALEOBANKS Phase 0 shadow owner | `PublicationReceipt` and `MediaOperatingSystem.shadow_publish` | Content record, operator, future analytics | Phase 0 permits `SHADOW_COMPLETED` with `external_effect=false` only | shadow negative controls |
| OpportunityPacket wire | Cross-repository ownership unresolved | `services/venture_protocol.py` v1.1 | DALEOBANKS and configured WMI intake | No unilateral incompatible change | `tests/test_wealthmachine_http.py` |
| VentureAssessment provenance | DALEOBANKS receiving boundary | `VentureAssessment.execution_class`, `evidence_class`, `external_execution` | API, drafts, decision memory | Mock label may only become stricter; it cannot be removed | `tests/test_idea_refinery.py` |
| Root authority | UNIIMENTE / Golden Kernel | external canonical source unavailable here | DALEOBANKS consequence gates | DALEOBANKS may tighten but not loosen | local Constitution and capability negative controls |

## Authority and event map

| Authority or event | Canonical definition | Authorized writer | Readers | Consequence gate | External effect |
| --- | --- | --- | --- | --- | --- |
| Account lifecycle | `AccountRegistry` status and declared authorization metadata | authenticated DALEOBANKS admin | API, media loop | prerequisite only; exact capability still required | none by itself |
| Exact delegated action | `CapabilityGrant` | approved human request through `CapabilityService` | executor | execution-time validate and consume | possible when a separate adapter is live |
| Publish attempt/result | `BaseSocialClient.publish` | platform adapter | decision ledger, operator | enabled + adapter live + kill switch + rate governor | possible only outside Phase 0 shadow path |
| Source/claim/content/localization | `MediaOperatingSystem` | authenticated DALEOBANKS admin/service | media operator | provenance and risk checks | none |
| Shadow publication receipt | `MediaOperatingSystem.shadow_publish` | shadow adapter | content record, operator | registered SHADOW account + adapter `live=false` | no |
| Real WMI assessment | configured WMI HTTP boundary | configured external endpoint | DALEOBANKS opportunity cockpit | packet approval + transport/contract checks | network request; no execution authority returned |

## Boundary decisions

- `services/media_operating_system.py` orchestrates existing owners; it does not generate drafts, mint capabilities, arm adapters, or score commercial opportunities.
- `services/account_registry.py` records current prerequisites; registry state never creates live authority.
- `constitution.md` remains a historical organ-local safety constitution until external Kernel ownership and migration are available. It may tighten behavior and may not be used to claim root sovereignty.
- PR #65 remains founder-intent lineage. PR #66 remains a separate publication-authority experiment. This branch does not rewrite, stack, or copy either one.
- WMI mock and inbound-unverified assessments remain visibly non-authoritative. Only a configured external HTTP execution is labeled external, and even that assessment prepares reviewable actions rather than executing them.

## Compatibility and deprecation

| Legacy path | Canonical source | Compatibility | Removal condition | Review trigger | Provenance retained |
| --- | --- | --- | --- | --- | --- |
| `AccountLane.active` | `AccountLane.status` through `AccountRegistry` | service synchronizes `active` only for historical readers | all readers migrate to lifecycle status and a schema migration is authorized | next account API revision | yes |
| citation-only `EvidenceLibrary` | structured `SourceRecord` and `ClaimRecord` plus existing citation recall | existing citation API remains | structured source ledger covers all existing callers | first production source ingestion | yes |
| WMI same-shape local mock | permanent execution/evidence provenance fields | contract shape retained with additive fields | never remove the mock label; fallback may be retired after real WMI reliability | real WMI end-to-end test | yes |
| direct X DM/like write path | future common consequence adapter | unchanged in Phase 0 | exact capability and unified receipt path cover direct actions | before enabling sensitive outreach | yes |

## Final decision

- Final state: `EXPERIMENT`
- Rationale: one reversible source-to-shadow transaction removes key identity, provenance, and simulation ambiguity while retaining existing mechanisms.
- Material dissent: internal correctness is not user or commercial proof; no further cathedral expansion before an authorized external evidence test.
- Rollback: close the draft PR or revert its additive files and fields; main and PR #65 remain untouched.
- Kill criteria: any unauthorized effect, credential material, inferred account, unlabelled simulation, broken test suite, or growing internal complexity without faster external evidence.
- Review trigger: Phase 0 reaches `CONTROLLED_CONTENT_LOOP_COMPLETION_RATE = 1/1`, CI completes, or PR #66 ownership changes.
