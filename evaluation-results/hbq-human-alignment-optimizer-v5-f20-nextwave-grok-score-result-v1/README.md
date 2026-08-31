# HANNA normalized next-wave Grok development result

This data-only package publishes the exact equal-group MAE projection for the
baseline and ten locally normalized next-wave candidates across the same three
f20 development prompt groups (33 cells total).

The lowest observed candidate is `normalized-nextwave-08-conservative-hybrid`:
MAE `0.75` versus baseline `0.9259259259259259`, an absolute difference of
`-0.17592592592592593` and a relative MAE reduction of `19%`.

**Evidence ceiling:** this is Grok development-only evidence from three groups
and 33 cells. Native endpoint contact cardinality is unproven. It does not
select a candidate, open confirmation, validate with Sol, establish a general
HANNA gain, permit endpoint pooling, promote anything, or grant runtime
authority.

The publication contains commitments and aggregate metrics only. It excludes
prompts, story text, human targets, raw model output, native identities, local
paths, and lifecycle identifiers.

Run `python verify.py` for a portable check of the exact four-file publication
inventory and its internal contract bindings. These bindings detect drift in
the bound files but are not an external signature or authenticity proof. Pass
the five private source paths documented by `--help` to replay all 33 persisted
cells through the portable pure projection without a provider call. No local
absolute source path is embedded in this public package.
