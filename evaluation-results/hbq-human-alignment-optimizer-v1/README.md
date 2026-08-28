# HANNA optimizer v1

This is a train/development-only protocol with a one-cell executor, not an optimizer runtime. It cannot claim a HANNA alignment gain.

The caller supplies two local roots: the frozen Fresh88 successor contract and the pinned HANNA CSV. Their bytes must match the contract hashes before the package derives the exact 80 generated items, 39 opaque prompt groups, and group-disjoint 48/13/19 split. No user-specific source path is embedded in this package.

Six candidate prompt/profile commitments are scheduled against both the 48-item train and 13-item development partitions for each provider: 732 prospective development cells. The 76-cell candidate-versus-control confirmation geometry is a future plan only. This package intentionally rejects every selection artifact and confirmation manifest until exact per-run/provider manifest recomputation exists.

Optuna tuple exploration is an optional provider-free legal-tuple scaffold. It returns factor tuples only: it accepts no score, result, aggregate, or selection. The DSPy adapter is likewise optional and never imported at runtime. It derives ephemeral local train-only examples from the exact pinned CSV and frozen successor: each contains the rendered candidate instruction/profile, the matched prompt and story, and the deterministic three-rater mean for each published HANNA dimension. Its declared six-dimension mean-absolute-error metric is a development-training diagnostic contract, not a result or selection rule. It emits no development or confirmation rows, calls no provider, and must never be placed in a public projection.

`offline_harness.py` is a provider-free candidate-generation harness. It reuses the source-bound split validation, deterministically derives six balanced candidates from the frozen 36-tuple control universe, and binds each candidate ID to its rendered instruction and profile bytes. It does not accept scores, results, confirmation material, or a selected candidate. Its optional Optuna adapter only explores legal factor tuples and is dynamically imported when explicitly called. Its DSPy surface is a deterministic, train-only data adapter with exact input/target byte commitments, not an optimizer, aggregate, model-output substitute, or selection path.

The execution-freeze derives 732 exact prospective cells from those roots, with six candidate commitments and paired Sol/Grok routes. It reconstructs one provider-ready payload only in memory, binding source and candidate bytes plus a six-dimension finite-score/evidence/coverage schema. Sol and Grok get exactly the same task, candidate, and schema bytes; route metadata is separate. Each route pins the reviewed HBQ-RS adapter transport identity, declares `paid_api:false`, and requires a trusted external zero-charge route receipt before any contact. It reserves two public-synthetic transport canaries, structurally excluded from every HANNA metric or selection surface; no canary proves transport until actually executed and validated. The untouched 76-cell confirmation plan remains structurally unreachable.

`executor.py` prepares exactly one named train/development cell into a new immutable directory. It persists the complete pre-contact disclosure (destination, exact request/prose/prompt/candidate/schema bytes, shared system instruction, route wrapper, adapter/parser/runtime hashes), externally supplied acknowledgement, and zero-charge receipt. Both gates are accepted only through an injected trusted local deployment verifier; the CLI deliberately cannot mint, select, or self-attest either gate. The approved integration calls `prepare_cell(...)`, then `dispatch_prepared_cell(..., allow_remote=True, trusted_gate_verifier=...)`. Dispatch recomputes the freeze, cell, effective request, wrapper, and gates before first contact; it writes a no-resend contact intent before calling the reviewed HBQ-RS OpenAI-compatible or Grok structured-output adapter.

Sol and Grok receive identical candidate/task/schema bytes and the same system instruction. Their transport wrappers remain independently pinned and are never pooled. Grok Build CLI does not attest reasoning; the executor opts into that known limitation only for Grok's explicitly provisional development-only/nonselector route and records the missing attestation. Any result remains unpromotable: the driver preserves native-message, content, and runner-failure artifacts but cannot mint a receipt until a later verifier recomputes one from complete raw-wire/session evidence. An unresolved written intent fails closed and cannot be resent.

```powershell
$env:PYTHONPATH='src'
# prepare always derives the execution freeze; it has no --execution-freeze flag.
python evaluation-results/hbq-human-alignment-optimizer-v1/prepare.py --frozen-successor-contract <frozen-contract.json> --hanna-csv <hanna.csv> --output-dir <new-freeze-dir>
python evaluation-results/hbq-human-alignment-optimizer-v1/validate.py --frozen-successor-contract <frozen-contract.json> --hanna-csv <hanna.csv> --split-manifest <split.json> --execution-freeze <freeze.json> --disclosure <disclosure.json>
# The command-line entrypoint fails closed. An approved local deployment integration must inject a trusted gate verifier;
# it may call prepare_cell(...) and then dispatch_prepared_cell(..., allow_remote=True, trusted_gate_verifier=...).
```

HANNA is human-reference context, not literary ground truth. A development selection is neither a production prompt nor a confirmed result.
