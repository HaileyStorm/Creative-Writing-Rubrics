# QPC24 exact-head successor v1

This is a provider-free freeze for the next QPC24 confirmation descendant of
QPC1. It is bound to CWR commit `4ce1204d8dd97feff2c7bd88237e265fac742adb`
and uses the current `prose.novel` eligible question sequence: 221 questions,
partitioned into nine 24-question provider calls plus one final five-question
remainder per complete-work evaluation.

QPC24 retains QPC1's three artifact roles—`author_original`,
`gpt_5_6_pro_rewrite`, and `public_control_story`—with five frozen repetitions
each. That is 15 complete-work logical evaluations, 150 future provider calls,
and 3,315 verdict positions. QPC24 does **not** mean 24 singleton requests.
Each future prompt visibly declares `WHOLE_WORK` and `complete` status, uses
the long-form `prose.novel` bundle, and covers every eligible question exactly
once per role-and-repetition evaluation. The final five-question batch is a
required remainder, never dropped or padded.

The current promoted figurative leaf is included with the unchanged ownership
controls: `penalty.purple_prose.metaphor`,
`core.freshness_and_non_genericness.no_default_metaphors`,
`penalty.purple_prose.proportion`, and `penalty.purple_prose.fatigue`.

No author-original or rewrite prose is stored here. `study.py` accepts a
separate controller at render time and verifies its role labels, exact source
commitments, whole-work scope, and schedule without writing private material.
Tests use only public synthetic controller material. The public aggregate plan
contains geometry and commitments only: no prose, prompts, expected labels,
model outputs, paths, sessions, requests, or per-call records.

The QPC1 sources are intentionally reused as a continuity-bound comparison;
they are not a disjoint holdout. QPC1 sessions, outputs, verdicts, and results
are not reused as QPC24 evidence. A local-only controller separately proves
the source lineage, all 150 prompt hashes, settled one-attempt rules, and the
zero-paid/no-fallback route before any execution may be considered.

## Local checks

From the repository root:

```powershell
.venv\Scripts\python.exe evaluation-results/hbq-qpc24-exact-head-successor-v1/study.py verify --controller <private-controller.json>
.venv\Scripts\python.exe evaluation-results/hbq-qpc24-exact-head-successor-v1/verify_output.py
pytest -q tests/test_hbq_qpc24_exact_head_successor_v1.py
```

Any source-head drift, runtime-hash drift, missing eligible leaf, incomplete
24-question partition, missing remainder, invisible whole-work scope,
aggregate leakage, provider contact, retry, resume, or post-holdout iteration
is a fail-stop. A later execution requires a separately reviewed, exact-binding
controller; this package authorizes nothing by itself.
