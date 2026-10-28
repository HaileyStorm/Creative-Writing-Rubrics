# Saved accepted-request operations

This snapshot copies existing operational summaries for808 accepted Dryad
requests,321 accepted Kyoto requests, and56 selected-repeat requests. It retains
the original total and arm groups, each metric's observed/missing counters and
existing sum, range, median, mean and nearest-rank90th percentile. It computes no
new statistics and contains no story text, human ratings, individual requests,
raw native metadata, account identifiers, private paths or runtime identifiers.

The populations contain accepted requests only. Failed, rejected and unadmitted
requests and resource waits are excluded; these summaries therefore understate
total collection operations and cannot estimate full study cost. Request counts
are not complete-story counts. Selected repeats are a selected reliability
population, not human-agreement measurements.

Native duration is the saved task-duration field. It is not isolated inference
latency, study wall-clock time or throughput. Time to first token is only the
recorded native field. Cached input and reasoning output are subset token counts;
do not add categories together. Missing fields remain missing. Observed-value
summary denominators are reported separately for each metric.

The ladder candidate uses the same HBQ parents and adds zero native judgments.
Its parent tokens are counted once under HBQ; local scoring cost is unmeasured.
These operations provide no billing, price, account-usage or quality-winner
claim. They do not independently attest model identity or backend settings.

## Observed accepted-request counters

The following input/output, duration and TTFT counters are observed for every
accepted request in each row. Other metric fields retain their own observed and
missing counts in the JSON. Duration is shown in milliseconds.

| Cohort | Accepted requests | Input tokens | Output tokens | Median native duration (ms) | Median TTFT (ms) |
| --- | ---: | ---: | ---: | ---: | ---: |
| Dryad DEV30 | 808 | 9,259,919 | 1,377,294 | 40,936 | 20,695 |
| Kyoto QSF12 | 321 | 3,821,080 | 592,729 | 38,605 | 18,437 |
| Selected TTCW repeats | 56 | 752,626 | 121,835 | 54,459.5 | 27,037 |

The [reader quality results](../hbq-reader-reference-descriptive-v1/README.md)
and [selected repeat results](../hbq-sol-ttcw-selected-repeats-20261026/README.md)
describe different outcome constructs. This table does not rank their efficiency.

## Provenance and reproduction

`aggregates.json` contains hash-only commitments to the reviewed operations
aggregate, its producer source and packet, admitted memberships, original source
receipts and joined views, and native metadata references. Hash commitments do
not expose or distribute the private source files.

The retained reviewed aggregate has SHA256
`d1e42e761274559c406ce3a80f30afc9540334e14d14d1a800cedb0c6e83c637`
and45498 bytes. The exporter accepts only those exact bytes and copies an
explicit field whitelist. It needs that retained aggregate to reproduce this
projection. This public snapshot cannot independently reconstruct the private
native counters. It makes no provider calls and runs no scoring or native replay.

With the retained reviewed aggregate available, use a new output file:

```text
python source.py --input <retained-reviewed-operations.json> --output <new-aggregates.json>
```

Output creation is exclusive and refuses an existing file. No timestamps or
machine-specific paths enter the generated snapshot.
