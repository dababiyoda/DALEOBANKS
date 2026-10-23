# Kernel boundary pin upgrade — 2026-10-23

Founder decision (2026-10-23, in the #196 session): "All organs should have upgraded pins."

## Pin

`uniimente-kernel-boundaries` moves from Kernel `4999acff` to Kernel `e7dc0cbc` (the head of
uniimente-kernel draft PR #196). The package version string stays 0.1.2 because the Kernel's frozen
proof missions check it. The pin is a commit, and the transport in that commit is newer. `4999acff`
is not an ancestor of `e7dc0cbc`: the 4999acff line was merged into the Kernel trunk by
reconciliation, not by fast-forward.

What the new pin gives this organ:

- **Per-organ keys.** `UNIIMENTE_BRIDGE_KEY_DALEOBANKS` is preferred over the shared
  `WEALTHMACHINE_SIGNING_KEY`. A message signed with it carries `X-Key-Scope: identity`, and a
  verifier holding only another organ's key refuses it. When the per-organ key is absent, the
  message falls back to shared scope, byte-identical to transport v2, so a peer still on 4999acff
  interoperates.
- No change to the wire contracts (1.0 and 1.1) and none to this organ's own code paths.

## Refinery

`services/idea_refinery.py`: an opportunity packet carries the thought's stated evidence, not only
its thesis:

- **What is kept:** later sentences that contain a figure, or that begin with "Evidence".
- **How it is kept:** verbatim and deduplicated, at most 4 sentences of at most 2000 characters
  each, after the `operator thought <id>` provenance item.

Before, a seed's figures never reached WealthMachine. The Kernel's 15-step mission recorded this
as step 9's gap. The figures are the operator's claims, carried as data: the refinery checks none
of them.

## Evidence

- `tests/test_idea_refinery.py`: three new tests. Two fail on the old refinery.
- Full suite: 387 passed on the new pin and 384 on the old pin, all of them before this change.
- Merge to `main` remains the founder's decision.
