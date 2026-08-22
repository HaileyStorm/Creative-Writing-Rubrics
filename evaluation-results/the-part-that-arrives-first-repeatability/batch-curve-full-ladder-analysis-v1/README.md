# Full batch-curve ladder analysis v1

Offline aggregation across the sealed V1 parent and completed V3 recovery. It
checks Git-byte-bound scorer inputs, public/private receipt geometry, accepted
evidence indexes, all thirty-one inherited prefix batches and their accepted
first attempts, the three retained quota rejections, exact V3 batch ranges,
and globally non-overlapping session commitments before recomputing all
thirteen frozen sizes. The public result contains aggregate metrics and
commitments only: no prompts, raw evidence paths, or session identifiers.

It makes no provider call and remains non-recommendatory.

The original V1 contract is retained and byte-bound as historical provenance.
Its registry/bundle assertions were already stale at its recorded Git head, so
this package does not upgrade that claim; the recomputation instead requires
the separately Git-byte-bound V3 analysis runtime.
