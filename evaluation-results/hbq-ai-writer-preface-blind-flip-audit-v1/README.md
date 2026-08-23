# Blinded audit of AI-prefix flip candidates

This small audit asks a narrow follow-up question: when the full fictional
AI-writer preface produces a stable failure and no preface produces a stable
pass, are the resulting criticisms supported by the text, and are they
material enough to justify a whole-leaf failure?

Nineteen completed comparisons matched that pattern: both full-prefix retries
were `NO`, while both no-prefix retries were `YES`. Three candidates had
verifiable exact evidence and were independently reviewed blind. Sixteen were
excluded because their stored exact evidence was incomplete. The exclusions are
part of the result, not failures treated as evidence.

All three reviewed criticisms were textually supported. Their materiality was
not settled: reviewer A called one material, one minor, and one borderline;
reviewer B called none material, two minor, and one borderline. Neither
reviewer called a criticism invalid.

The useful inference is limited. The preface appears to improve sensitivity to
real issues in this small slice, while its scope or materiality specificity may
fall. That supports keeping evidence requirements strict and calibrating the
scorer's escalation to a binary failure. It does not establish that every
prefix-only failure is correct, that the preface identifies authorship, or that
the result generalizes beyond the audited slice.

The audit cannot answer whether one-question-at-a-time execution differs from
batched execution; it did not vary question-per-call geometry. It used no paid
evaluation and no new or live human judging.

Only aggregate counts, labels, and one-way commitments are public here. The
underlying prose, prompts, responses, identifiers, exact evidence, and local
locations remain private. See [`results.json`](results.json) and
[`source-commitments.json`](source-commitments.json) for the machine-readable
record.
