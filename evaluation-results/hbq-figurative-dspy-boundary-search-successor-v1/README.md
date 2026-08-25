# Figurative DSPy boundary-search successor v1

This is a development-only, static boundary search for
`penalty.purple_prose.metaphor`. It follows the isolated-anchor pilot's
valid-but-mixed 5/6 result without reusing that pilot's fixtures, prompts,
calls, notes, or outputs. It does not alter rubric wording, leaf identity,
owner, weight, split, QPC24, or Gray Blood state.

Four appendices are frozen in `candidate-appendices.json`: the manual
treatment and three bounded variants. They clarify compatible dimensions,
artifact-supported semantic hinges, and unsupported competition. They are not
generated during execution and require no DSPy runtime dependency.

The public corpus contains 12 TRAIN cases across six boundary types and six
disjoint DEV cases. Expected labels live only in the external private ledger;
they are not present in provider prompts. The planned geometry is 48 singleton
TRAIN calls (four candidates by 12 cases), followed only after deterministic
ranking by 24 singleton DEV calls (two candidates by six cases by two repeats).
Selection is exact-label performance, then boundary-type stability (the lowest
correct count across the six TRAIN boundary types), then frozen candidate ID
after rejecting any ownership failure; it requires independent Sol review. A later confirmation and
holdout are separately gated.

Provider-free preparation materializes and hashes all TRAIN plus all potential
DEV provider-visible catalogs, inputs, contracts, overrides, commands, and
rendered prompts. Only the selected two candidates can later dispatch the 24
DEV calls. The only mode used for this freeze is:

```powershell
python run.py --dry-run --private-root <fresh-private-root>
```

The only provider-capable form is intentionally sealed until that independent
review; it is shown here so any future release is explicit:

```powershell
python run.py --execute --private-root <fresh-private-root> --allow-remote --acknowledge-zero-incremental-charge
```

It permits GPT-5.6 Sol/high only, one call per candidate/case, one physical
attempt, zero retries, no normalization, source-exact quotation, public
synthetic provider input only, zero incremental charge, and no paid fallback.
There were zero provider calls in this package freeze.
