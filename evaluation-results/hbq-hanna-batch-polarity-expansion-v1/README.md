# HANNA batch/polarity expansion v1

This is a sealed development-only expansion of the completed one-story pilot. It reuses the complete `hanna-225` three-repetition matrix (198 verified session commitments) and schedules three new stories: `hanna-178`, `hanna-817`, and `hanna-382`. Each new story has the same 3 × 66-call factorial matrix, for 594 new calls and 792 combined commitments.

The condition order is fixed by the four Latin rows in `study-contract.json`: `225` uses L0/L1/L2; `178` L1/L2/L3; `817` L2/L3/L0; `382` L3/L0/L1. The package must freeze its deterministic twelfth-story selector before any attempt directory exists. That selector only closes the repeatability-prefix bookkeeping gap; it does not alter this four-story package.

`study.py` contains the plan verifier and offline analyzer. `run_expansion.py` can prepare an immutable execution contract and dry-run the exact 594-call schedule, but its command-line interface deliberately has no execution mode. A reviewed caller must explicitly supply a one-attempt callback; failures freeze the run and never retry. Public artifacts contain commitments only; prompts and responses remain under the supplied private root.

Confidence is a repeat-consensus diagnostic, not calibrated truth. Cross-story HANNA correlations are exploratory and are only computed from an offline caller-supplied published-label mapping. No provider calls or fresh human judging are made by this package.
