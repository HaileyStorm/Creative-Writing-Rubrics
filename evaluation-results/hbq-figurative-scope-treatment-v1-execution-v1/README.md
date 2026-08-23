# Figurative scope treatment execution v1

This is the execution successor to the frozen public synthetic development package at commit `17b2881`. It reuses that package's 28 cells without copying its corpus, then schedules exactly two arms and three repetitions per cell: 168 direct v4 one-leaf Codex calls.

`baseline` has no task contract. `scope_rendering_only` supplies a strict, otherwise empty task contract plus the reviewed v1 compatibility decision required by the repaired v4 direct-judge route. Each call uses `codex`, `gpt-5.6-sol`, `high`, and `batch_size=1`. The provider receives only an opaque artifact filename/ID, prose, the selected leaf, and (for treatment) ordinary scope context. Case IDs, arm IDs, expected verdicts, and controller labels stay in the private schedule.

Prepare and inspect the study without a provider call:

```powershell
python run.py --dry-run --private-root C:\private\hbq-figurative-scope-execution-v1
```

That root must be outside this repository. It contains copied synthetic inputs, contracts, ordinary CWR run directories, checkpoints, and the private settlement. `--dry-run` runs every slot through CWR's real direct-v4 dry-run, renders the exact prompts, and makes zero provider calls. `--execute --allow-remote --acknowledge-zero-incremental-charge` resumes those prepared slots; `--resume` does the same after interruption. No provider call is made by `--dry-run`.

`python study.py verify` checks the predecessor, prompt-repair, schedule, and privacy bindings. `python study.py settle --private-root ...` validates completed CWR manifests/checkpoints, model/reasoning/run identity, and grounded evidence, then writes a private settlement and an aggregate-only public summary in that external root. There is no holdout, DSPy path, fallback provider, or statistical promotion claim here.

The settlement requires unique accepted Codex provider sessions. CWR's rejected-retry sanitizer does not retain rejected Codex session IDs, so this successor records rejected attempt counts but makes no all-attempt session-uniqueness claim.
