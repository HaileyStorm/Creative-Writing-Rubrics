# Ox Alpha HANNA comparison v2

This is the separately frozen successor to the unexecuted v1 protocol.  It compares exactly three outcome-blind public HANNA stories (`hanna-827`, `hanna-957`, `hanna-201`) against the sealed Fresh88 development verifier matrix: 178 static `prose.short_story` leaves plus `task.contract.hanna.prompt_response`, or 179 leaves total.

The run is serial: six 32-leaf batches per story, 18 logical requests and at most 36 physical HTTP attempts. It is zero-cost and provisional-only; GPT-5.6 remains the primary condition.

`prepare_pilot.py` derives the GPT reference offline from the Fresh88 execution contract, verifier matrix, semantic gate, and repair1 artifacts. It does not use the invalid canonical-v3 public analyzer and makes no provider call. The frozen secondary result is an explicit 178-static-leaf ablation for both systems; it is not the primary score and any Relevance reading remains a two-leaf noncanonical ablation.
