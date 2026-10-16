# Bounded simulated community feedback

The existing FeedbackService → MemoryService → Generator path now has an explicit offline simulation. Unsupported popular feedback, ties and regressions are recorded as evaluation actions without creating lessons. A source-supported correction must improve separate held-out tasks with all answers correct before an improvement note is retained. The later Generator draft rechecks its source; conflicting facts and arbitrary instruction notes produce abstention.

Supported task: deterministic source-backed simulated replies. No LLM, publication, participant contact, policy change or authority increase. Existing social generation is not silently replaced.

```bash
EMBEDDINGS_PROVIDER=hash PERSIST_STORE=false python -m pytest tests/test_community_feedback_demo.py -q
```

The fixture contrasts misleading engagement 100000 with legitimate criticism at engagement 1. Correctness improves from 1/2 to 2/2 on two held-out tasks, and a later Generator draft changes. Repetition produces no improvement; a conflicting candidate regresses and is rejected. Receipts: `tests/evidence/greg-community/`.

No real participant outcome was measured. A consented pilot must establish baseline/unseen follow-up task correctness, completion time/help requests, delayed retention and errors/harm, including nonresponders. Engagement and follower counts stay separate.

Intent is the current founder request and Kernel INTENT-0030/embodied/first-body records. The Kernel's GREG integration decision contains the shared five-role, two-pass review. This is one contributor's reversible implementation, without independent evaluation. Rollback: leave the draft unmerged or revert these additions while retaining evaluations and lessons as history. No service was installed or activated.
