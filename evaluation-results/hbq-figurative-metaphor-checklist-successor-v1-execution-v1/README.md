# Figurative checklist Phase A executor v1

This unexecuted successor binds the public synthetic figurative checklist
freeze at `a02418f` to 72 Phase A calls: eight fixtures, three independently
owned leaves, and three repeats.  Each is a current-production, one-leaf
Codex GPT-5.6 Sol/high call with batch size and attempts fixed at one.

`--dry-run` freezes the private runtime and successor bindings before running
the real CWR command shape into a separate dry-run directory, renders the exact
current prompts with the same minimal child environment, then rejects any
binding drift observed during rendering. It freezes the preexecution
disclosure and makes zero provider calls. The explicit private root must be
outside and disjoint from CWR; a failed or drifted dry root is abandoned rather
than repaired in place.

`--execute` is the only remote surface.  It requires `--allow-remote` and
`--acknowledge-zero-incremental-charge`, has no resume path, rejects an existing
durable execution claim, populated run directory, or terminal settlement,
prohibits paid fallback, and persists CWR format-5 `terminal_sidecar_v1`
evidence. Do not use it until independent review authorizes a live Phase A run.

Before any provider-capable subprocess, `--execute` atomically creates a
durable root-level execution claim that hashes the frozen manifest, runtime
schedule, disclosure, and authentication receipt. The claim survives a crash, incomplete
settlement, or terminal result, and every later invocation fails closed: this
successor deliberately has no retry or resume surface.

The disclosed destination is exactly `Codex CLI -> authenticated OpenAI
service`, authenticated through the current ChatGPT subscription rather than
an API billing key.  Dry-run freezes the resolved `codex.exe` path, bytes hash,
version output, `codex login status` hashes/status, and a minimal child
environment with OpenAI/Codex billing credentials absent.  Execute reruns this
check immediately before dispatch and fails before contact on any drift.

Settlement requires the exact durable execution claim, then reads actual CWR
run manifests, lifecycle sidecars, checkpoints, prompts, provider response
receipts, model/reasoning fields, and exact quoted evidence. It accepts no
caller-supplied verdict records. Results are
aggregate-only and write-once.  Phase B remains disabled even if Phase A finds
the two stable cross-stratum misses that would otherwise make it eligible; no
real holdout is opened and nothing is promoted.

```powershell
python run.py --dry-run --private-root C:\path\outside\CWR
python run.py --execute --private-root C:\path\outside\CWR --allow-remote --acknowledge-zero-incremental-charge
```
