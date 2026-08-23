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

For the unchanged v1 analyzer, the private adapter projects only already-grounded `exact_quote` evidence. It keeps mixed summary evidence in the private successor record and never synthesizes quotes; a summary-only result fails closed.

## Aggregate result

The 168 planned calls were accepted with zero rejected calls. The aggregate-only result is [`public-result.json`](public-result.json), projected from private aggregate `417cdd726711062ec3d1ad29924d605453fe17366e9602c927d8e9cf377304b8` without paths, prose, slots, requests, sessions, or raw evidence.

The result is `NO_GO`. `scope_rendering_only` reached stockness 34/36, proportion/material load 27/36, fatigue 12/12, isolated revision-note materiality 1/3, recurring material failure 3/3, excerpt CANNOT_ASSESS 3/3, and schema/evidence/provenance 84/84. It did not pass the frozen treatment gates; controls were 9/12 in each arm, so there was no control regression. No rubric wording, leaf ownership, split, or weight is promoted. DSPy remains development-only should a later simple manual repair prove inadequate; QPC24 and the Gray Blood rebaseline remain held until the treatment is stable.

The zero-incremental-charge route is owner-attested as a subscription route, not independently verified billing evidence.
