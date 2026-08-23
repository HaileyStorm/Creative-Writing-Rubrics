# Figurative scope DSPy successor v2

This frozen, development-only successor repaired three ambiguous TRAIN controls
without changing the prompt candidates, HBQ-RS rubric, leaves, ownership,
splits, weights, bundles, schemas, or runtime. Candidate instruction text,
synthetic text, controller labels, selection material, prompts, responses,
evidence, receipts, and held content remain private.

The original freeze planned reuse of 28 accepted unaffected TRAIN rows and 36
new singleton TRAIN calls, with selection only after both candidates passed the
composite TRAIN gate. The actual run settled incomplete before that design could
be scored: two logical TRAIN calls occurred, one yielded a grounded
expected-YES/observed-NO miss, and one ended terminally as
`schema_or_quote_failure`. The terminal call was a schema-valid mixed
`exact_quote`+summary response rejected by the v2 validator. There were no
retries. Selection was neither accessed nor read; confirmation was not
accessed.

The aggregate-only result is [public-result.json](public-result.json), pinned
by SHA-256 `f2128d0f9868d3608a739a6e10bbbb733f22f1117c479b87caf3115059603753`.
Its private source lineage is bound by the contract, including execution commit
`7febc77483f674a929d1778b7285a3a02c4d3a5a`; it does not expose private run
content. The settled decision is `NO_PROMOTION`: this result promotes no
prompt, rubric wording, leaf, ownership, split, or weight change.

`python run.py --dry-run` is provider-free and verifies the contract, result
hash, lineage, counts, and privacy surface. `--execute` is permanently refused
because this v2 study is settled; a successor must use a separately frozen
package rather than mutate or resume this evidence.
