# DALEOBANKS Foundry Signal Adapter

DALEOBANKS observes public signals and prepares OpportunityPackets. It does not possess the commercial facts required to declare that an opportunity is ready for institutional construction.

`services/foundry_adapter.py` creates a versioned, proposal-only Foundry envelope. Existing packet fields such as `buyer_type`, `customer_segment`, and `audience` remain hypotheses. A named buyer, pain owner, budget owner, recurring transaction, trapped value, accepted artifact, external consequence, lawful path, and evidence must be supplied from accountable human input or external evidence.

The adapter always emits:

- `requires_human_approval: true`;
- `execution_authority: none`;
- a content-addressed source-packet digest;
- explicit missing fields;
- `ready_for_foundry: false` until the governing transaction is complete.

The adapter performs no network request, publishing, payment, approval, or execution.

## Intended flow

```text
DALEOBANKS signal
-> OpportunityPacket
-> Foundry signal envelope
-> accountable completion of missing commercial facts
-> canonical UNIIMENTE Foundry intake
```

The envelope is evidence input, not authorization. Kernel policy, capability grants, human ratification, and the Consequence Gate remain separate requirements.
