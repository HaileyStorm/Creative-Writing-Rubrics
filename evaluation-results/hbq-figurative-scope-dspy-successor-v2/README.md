# Figurative scope DSPy successor v2

This frozen, development-only successor repairs three ambiguous TRAIN controls;
it does not change the prompt candidates, HBQ-RS rubric, leaves, ownership,
splits, weights, bundles, schemas, or runtime. The candidate instruction text,
synthetic text, controller labels, selection material, prompts, responses,
evidence, receipts, and all held content remain outside this public package.

There are no proposer calls. Two hash-bound candidates from v1 reuse exactly
14 accepted, exact, evidence-valid unaffected TRAIN rows each. Each candidate
then receives three repetitions of the three corrected artifacts against both
leaves: 36 new singleton TRAIN calls total. Selection stays closed unless both
candidates pass all 14 reused and all 18 fresh rows. If that composite gate
passes, both candidates receive two repetitions over eight untouched selection
cells: exactly 32 selection calls. Confirmation is never opened by v2.

Failure at either scored gate is `NO_GO`. If both candidates pass selection,
the shorter frozen candidate wins the predeclared tie and the result is
`READY_FOR_SEPARATE_CONFIRMATION_FREEZE_REVIEW`; that status is not permission
to inspect or run confirmation. The initial checked-in status is
`PENDING_EXECUTION`.

The provider-free verifier and dry run do not import DSPy or call a provider.
Remote development execution requires an explicitly supplied private root,
hash-matching private engine and freeze inputs, `--allow-remote`, and
`--owner-zero-incremental-charge`. Only the Codex ChatGPT-subscription route is
allowed; paid/API-compatible and fallback routes fail closed.
Every new call uses the durable `terminal_sidecar_v1` start-and-settlement
lifecycle. Malformed response topology or ungrounded evidence is a terminal
incomplete outcome, not a retry or a scored miss.

## Private freeze bindings

The public contract binds the frozen private implementation with two
64-character lowercase SHA-256 values:

- `bindings.private_engine_sha256`
- `bindings.private_freeze_inputs_sha256`

Both fields are finalized. Dry-run verification confirms the bindings without
loading the private engine or authorizing selection, confirmation, or any
provider call.
