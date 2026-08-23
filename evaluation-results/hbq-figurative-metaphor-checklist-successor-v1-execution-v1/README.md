# Figurative checklist Phase A executor v1

This unexecuted successor binds the public synthetic figurative checklist
freeze at `a02418f` to 72 Phase A calls: eight fixtures, three independently
owned leaves, and three repeats.  Each is a current-production, one-leaf
Codex GPT-5.6 Sol/high call with batch size and attempts fixed at one.

`--dry-run` runs the real CWR command shape into a separate dry-run directory,
renders the exact current prompts, freezes the private runtime bindings and
preexecution disclosure, and makes zero provider calls.  The explicit private
root must be outside and disjoint from CWR.

`--execute` is the only remote surface.  It requires `--allow-remote` and
`--acknowledge-zero-incremental-charge`, has no resume path, rejects any
pre-existing execution directory, prohibits paid fallback, and persists CWR
format-5 `terminal_sidecar_v1` evidence.  Do not use it until independent
review authorizes a live Phase A run.

Settlement reads actual CWR run manifests, lifecycle sidecars, checkpoints,
prompts, provider response receipts, model/reasoning fields, and exact quoted
evidence.  It accepts no caller-supplied verdict records.  Results are
aggregate-only and write-once.  Phase B remains disabled even if Phase A finds
the two stable cross-stratum misses that would otherwise make it eligible; no
real holdout is opened and nothing is promoted.

```powershell
python run.py --dry-run --private-root C:\path\outside\CWR
python run.py --execute --private-root C:\path\outside\CWR --allow-remote --acknowledge-zero-incremental-charge
```
