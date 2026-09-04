# Child20: four-story Grok TRAIN screen

The unchanged child20 prompt reduced equal-group MAE from **1.041667 to
0.708333 (32%)**, improving all four newly measured TRAIN groups.

This is a small development screen, not confirmation or evidence of a new
generalization gain. The eight cells pair baseline and child20 on four fixed
Fresh88 TRAIN stories; every response and all six numeric dimensions are
included. The [receipt-derived result](result.json) was independently replayed
against raw responses and CSV target means, with eight distinct request IDs
and eight distinct session IDs. Native endpoint contact cardinality remains
unproven.

Judge: xAI Grok Build subscription, requested `grok-4.6`, reported
`grok-4.6-build`; tools, web search, and subagents disabled. Human target scores
were not included in provider prompts. This screen opens only the planned unchanged-payload Sol-8
measurement; no Sol result or runtime promotion is claimed here.

The [frozen screen implementation](../hbq-human-alignment-optimizer-v11-child20-train-screen-v1/)
at `dc7b59a` reconstructs the source mapping, exact baseline/child20 payloads,
and receipt-only report. Existing Fresh96 confirmation results remain
separate. Local source prose and native request/response bodies are not
published in this aggregate-only artifact.
