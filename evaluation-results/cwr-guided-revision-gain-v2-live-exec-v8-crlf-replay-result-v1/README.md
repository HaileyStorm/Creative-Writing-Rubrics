# V8 CRLF replay result

V8 is a provider-free result package for an explicitly supplied, completed V7
endpoint run. It pins V7 commit `1affc2c` and executor SHA-256
`f2e35ea8380fb50e5c657ecc4d9ecc47128d044a56d6e2ce5ca4ef0e58aa5865`.

It retains every V7 receipt, identity, admission, inventory, schema, control,
and projection check. The sole repaired replay condition accepts adapter stdout
only when the bytes are exactly `json.dumps(envelope, sort_keys=True)` in ASCII
followed by exactly one LF or CRLF. The persisted adapter-control artifact
remains canonical LF-only.

## Local-only prerequisites and command

`--source-root` supplies only the completed V7 run. V8 then loads the pinned
V7 executor, whose replay logic also requires its hardcoded immutable V6
lineage-root identity `cwr-revision-gain-v6-replacement-c24a9ec-20260831a`, V6
executor SHA-256 `e0f4181e4daed637b6c8e438e71b90129505bd2191202dd2ef43e0f7e406d172`,
frozen-target-root identity `cwr-revision-gain-v6-targets-c24a9ec-20260831a`,
and target-manifest SHA-256
`c139d7868f0226b2e507baa47c19f2b90adac1ee5ad7856bc12648972d7ae71a`.
Those dependencies are intentionally not copied into this public result and
their local locations remain V7 implementation details.

Use the command only on a local checkout where the exact V7 hardcoded V6 and
target dependencies are already present and validate at their expected local
locations:

`python executor.py --source-root <absolute-completed-v7-root> --output result.json`

The published result omits the supplied source-root path and performs no
provider, queue, or remote action. Off-host replay is **NO-GO** until the exact
V6 dependencies are supplied or reconstructed at the pinned identities and
required local layout, or a future explicit-input successor replaces V7's
hardcoded dependency contract.

The output is endpoint-separated: 16 guided-control and 32 arm-baseline rows.
It makes no provider-ranking or generalization claim. Sol native contact
cardinality is unproven; the launch intent is inherited from V7; and Grok
command-identity semantics are not cross-compared to the route proof.
