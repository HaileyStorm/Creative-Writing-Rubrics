# Whole-poem architecture execution successor v1

This is a provider-free freeze for the reviewed whole-poem architecture wording treatment. It creates a fixed 42-slot singleton controller: 21 current-wording technical controls first, followed by 21 candidate targets in the same fixture/repeat order.

Current controls have no semantic expected-label ledger. Candidate labels are not provider-facing, not an at-rest secret, and are never rendered into prompts or the public schedule; the required external private root keeps them separate only to prevent accidental use during a call. A future adapter must start every call in a fresh neutral empty directory with no repository or private-ledger access and pass only the frozen prompt through standard input. This package cannot make provider calls; it only verifies the freeze and prepares immutable private controller artifacts.

Each slot permits one physical attempt. Retries, replacement, resampling, extension, and resume are forbidden. A control technical failure stops before candidate targets. A candidate technical failure consumes its attempt and leaves the run technically incomplete; semantic candidate misses are recorded and do not stop the remaining targets. Semantic settlement requires all 42 valid terminals and never promotes a wording or rubric change.
