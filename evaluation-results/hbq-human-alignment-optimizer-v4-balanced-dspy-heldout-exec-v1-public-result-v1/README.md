# HANNA heldout public result (v1)

This versioned descendant publishes the compact, independently replayed result
from the 66-cell heldout development schedule without publishing stories, human
targets, per-cell observations, raw model responses, local paths, or endpoint
request/session identifiers.

`grok-selection.json` is the exact canonical Grok-primary selection frozen
before Sol evidence was opened. `endpoint-result.json` is the exact canonical
endpoint-separated result returned by the committed two-phase analyzer.
`public-result.json` is a compact presentation of those immutable artifacts,
and `provenance.v1.json` pins their producer and source commitments.
The producer contract, producer source, schemas, and `feedback-*.json` files
form the minimal authority bundle consumed by the governed v3 generator. The
materializer can emit its machine-local absolute-path descriptor with
`--feedback-output`, `--wave-id`, and `--seed`; no absolute paths are tracked.

The result is a Grok-specific development improvement, not general gain. The
selected candidate reduced four-group Grok MAE from `1.0694444444444444` to
`0.875`, but increased two-group Sol MAE from `1.3680555555555554` to
`1.4277777777777778`. Endpoints are not pooled. Sol native endpoint/contact
cardinality remains unproven, the confirmation partition remains unopened, and
DSPy/Optuna have no runtime authority.

Run `python verify.py` for the provider-free internal verification. Regeneration
uses `materialize.py` with explicit immutable evidence paths; it never contacts
a provider.
