# Platform Automation Matrix

What exists, per surface. `IMPLEMENTED` means code and tests; `SHADOW` means
it runs with external effects refused; `NOT BUILT` means absent, not planned
into existence by appearing here.

Do not assume a connector exists because a platform is named. Most of this
table is empty on purpose.

## Current surfaces

| Platform | Adapter | State | Live capability | Accounts |
| --- | --- | --- | --- | --- |
| X | `services/x_client.py` | `IMPLEMENTED`, historical | refused — `LIVE=false`, no account registered | 0 |
| LinkedIn | `services/linkedin_client.py` | stub | none | 0 |
| Mastodon | `services/mastodon_client.py` | stub | none | 0 |
| TikTok, Instagram, YouTube, Facebook, Reddit | — | `NOT BUILT` | none | 0 |
| Podcasts, newsletters, search, web | — | `NOT BUILT` | none | 0 |
| WhatsApp / Telegram | — | `NOT BUILT` | none | 0 |

Shadow publication runs through `BaseSocialClient` with `live=false`. The
base class fails closed: a production adapter on the Phase 1 path raises
rather than degrading to a real call.

## What every adapter must carry before it goes live

Per the platform-network requirement. An adapter missing any row is not
eligible for live authority regardless of whether its code works.

- platform identity and account identity
- authorized capabilities, enumerated — not implied by the API surface
- posting limits and rate limits
- permitted content classes
- risk class
- credential owner and credential *reference* — never credential material
- revocation state
- evidence requirements
- rollback and freeze mechanism

`IMPLEMENTED`: the account registry holds identity, lifecycle, posting
limits, risk class, disclosure requirements, and credential references
(`env:`, `vault:`, `secret-manager:` only). `NOT BUILT`: per-adapter rate
limit and permitted-content-class binding.

## Account lifecycle

```
PLANNED → SHADOW → ACTIVE → PAUSED → FROZEN → RETIRED
                      ↓
                 COMPROMISED
```

Registered accounts today: **0**. Languages active: **0**. Platforms active:
**0**.

## Production tooling

`ASPIRATIONAL`. HeyGen, Captions, Zapier, browser automation, computer-use
agents — treat each as a replaceable adapter behind an interface. None is
integrated. Do not vendor-lock the architecture to any of them.

## Automation discipline

Every automation must be versioned, bounded, observable, reversible,
testable, owned, documented, and revocable. No uncontrolled chains: an
automation that triggers another automation needs an explicit budget and a
stop condition, or it is not eligible to run.
