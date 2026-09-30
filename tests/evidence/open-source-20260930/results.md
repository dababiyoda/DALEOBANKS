# Open-source AI validation — 2026-09-30

Execution: separate MarcoPolo scratch workspace after attached cloud executor
startup failed. Python 3.11.16; Node 22.23.3. Public source checkouts only.
No real model service, model downloads, secrets, production activation or paid
provider calls were used. Protocol replies are controlled fixtures.

Kernel source containing executable changes: 2ba2f02d2887356270c12da3733a73deeeb70dd6
(later commits add intent/setup documentation only).
DALEOBANKS source: b4b98e070d43d52d176745f2a2eac2c3fbaa9688.
God's Eye executable source: 59e5bec8a97fd7579ed45ab1ed773c9d4a0f7947
(later documentation changes do not alter executable source).

Commands executed in their repository checkouts:

    python -m pytest tests/unit/test_local_model.py tests/unit/test_egregore_runtime.py -q --tb=short
    38 passed in 3.46s

    python -m pytest tests/test_local_models.py tests/test_llm_harness.py tests/test_embeddings.py tests/test_semantic_index.py tests/test_config.py -q --tb=short
    44 passed in 4.35s

    node --test --test-reporter=spec src/localAiProvider.test.mjs src/hudSummaryResponse.test.mjs src/voice/realtimeBackend.test.mjs
    14 tests; 14 pass; 0 fail; 0 skip

    git diff --check origin/main HEAD
    passed for all three executable candidates

Kernel negative result preserved: initial fixture 37 passed / 1 failed because
ResourceGovernor(max_estimated_cost_usd=0) correctly hibernated before inference.
Fixture corrected to a positive reserve ceiling with zero estimated token cost.
DALEOBANKS initial focused run: 38 passed; six additional embedding protocol and
malformed-vector controls produced the final 44.

Tested effects: real loopback mock HTTP completion, JSON draft scope and evidence
binding, idempotent retry, timeout/token configuration bounds, hosted/credential URL
refusal, redirect refusal, existing-key billing prevention, configured local chat,
local embedding request/normalization, malformed vector hash fallback, model-aware
tags, existing prompt/schema/memory/config regressions, local HUD and realtime
opt-in boundary, existing token/SDP cancellation and installed keyless HUD route.

Limits: no model-quality benchmark, no hardware capacity test, no full suites,
no Docker build, no production deployment, no independent human verification.
God's Eye's documented supported Node runtime is 24.14+ or 26; focused Node 22
test evidence is not supported-runtime build evidence. Local realtime speech
remains unimplemented. No whole-institution operational claim is established.
