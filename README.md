# Creative-Writing-Rubrics

**CWR 1.2.3 ships HBQ-RS 1.2.1**: a local-first toolkit for turning a review
brief into small, inspectable questions about creative work, then aggregating
the answers deterministically. It supports draft review, critique, model and
dataset evaluation, benchmarking, and synthetic-data workflows without hiding
the rubric, coverage, or uncertainty behind one opaque score. It does not turn
a literary judgment into an unquestionable truth.

The current HBQ-RS content contains **278 modules**, **2,145 atomic leaves**,
and **85 bundle presets**. A judge answers one yes/no leaf at a time;
aggregation is code, not another model call. Stable module, question, criterion,
and bundle IDs are the public contract.

## What the public evidence says

The strongest public evidence is deliberately bounded:

- In the [established-rubric repeatability study](evaluation-results/the-part-that-arrives-first-repeatability/established-v4/), one complete authorized story was judged five times with GPT-5.6 Sol. HBQ-RS had 91.01% all-five leaf agreement, 97.08% mean modal-label agreement, and no total-score ceiling; the comparison rubrics were more ceiling-bound on this case. This demonstrates repeatability and available headroom for one story, not general validity or literary superiority.
- The [Gray Blood full-book V9 aggregate](evaluation-results/hbq-gray-blood-full-book-qpc24-rebaseline-v9-public-result-v1/) is a settled full-fidelity aggregate for a work-in-progress manuscript, with no sampling: author-original `63.0202` (8 units / 1,817 positions) versus the explicitly labeled GPT-5.6 Pro rewrite `73.2369` (7 units / 1,589 positions), a difference of `+10.2167`. The non-statistical result is diagnostic for this rubric, scope, and frozen design, not a general ranking.
- The primary [Fresh88 generated-only HANNA analysis](evaluation-results/hbq-human-alignment-v3-fresh88-overlap-analysis-v1/) is negative: across 80 generated stories, final-score Spearman was `-0.0441` and the six-dimension macro was `-0.0361`. Current evidence does not demonstrate human-reference alignment.
- A [four-cell Sol descriptive follow-up](evaluation-results/hbq-human-alignment-optimizer-v5-grok-descriptive-sol-validation-result-v1/) on two development prompt groups observed equal-group MAE `0.9236111111111112` for `candidate-102cc7f06c9a99a7` and `0.788888888888889` for `candidate-69720ac6257db007` (`-0.1347222222222222`, a `14.586466165413528%` relative reduction). Its local Codex lifecycle does not prove native endpoint contact cardinality; it is neither selection nor confirmation evidence, does not establish general HANNA alignment, and does not pool endpoints or grant promotion/runtime authority.
- The [next-wave Grok HANNA development result](evaluation-results/hbq-human-alignment-optimizer-v5-f20-nextwave-grok-score-result-v1/) covers three frozen development prompt groups and 33 cells: baseline equal-group MAE `0.9259259259259259` versus `0.75` for `normalized-nextwave-08-conservative-hybrid` (a `-0.17592592592592593`, `19%` reduction). Its [development-only optimizer readout](evaluation-results/hbq-human-alignment-optimizer-v5-f20-nextwave-development-optimizer-v1/) completed all `198/198` Optuna `4.9.0` grid trials; DSPy `3.3.1` validated 11 frozen evidence examples and signatures with zero LM calls. Candidate 08 won all 18 low-penalty settings, while strong robustness penalties flip to candidate 04. An unchanged [six-cell Sol validation](evaluation-results/hbq-human-alignment-optimizer-v5-f20-nextwave-sol6-validation-result-v1/) over the same three groups moved in the same direction, from `1.252777777777778` to `1.1351851851851853` MAE (`9.39%` relative reduction). These are small development results, not confirmation or general alignment: endpoints remain separate, native contact cardinality is unproven, and the evidence grants no promotion or runtime authority.
- The [CWR-guided revision V8 result](evaluation-results/cwr-guided-revision-gain-v2-live-exec-v8-crlf-replay-result-v1/) independently recomputes 40 endpoint judgments, including 16 guided-control and 32 arm-baseline comparisons. Every guided-control comparison was positive: mean holistic/compact differences were `+2.25`/`+2.25` for Sol and `+1.75`/`+1.50` for Grok. Endpoints remain separate; Sol contact cardinality is unproven, local-only replay depends on exact V6 inputs, and the result makes no provider-ranking or generalization claim.

![Five-run native-scale score distributions](evaluation-results/the-part-that-arrives-first-repeatability/established-v4/results/score-distributions.svg)

*Five repetitions of one story, keeping each rubric on its native scale. The
chart is a repeatability view, not a cross-rubric quality ranking; its numbers
and SVG are bound by the study's result manifest and verifier.*

These results show what the system can make inspectable today: repeatability,
scope-aware reports, explicit uncertainty, and bounded comparisons. They do
not complete human-alignment validation, establish reader outcomes, or create a
default hierarchy of literary quality.

## Active work, not results

The [V8 multisample continuation](evaluation-results/hbq-multisample-repeatability-v1-remainder-capacity-reset-successor-v8/)
is an **unpublished, paused operational checkpoint**, proceeding one settled,
trace-bound sequence at a time. Its exact live sequence count is not promoted
here; it becomes a public repeatability result only after completion and
integrity-checked analysis.

The committed study packages make the next questions reproducible without
pretending they have answers yet:

- [HANNA optimizer v3](evaluation-results/hbq-human-alignment-optimizer-v3/)
  freezes five prompt candidates, the corrected 80-item/39-prompt-group
  Fresh88 geometry, and disjoint 48/13/19-item train/development/confirmation
  partitions. Its [native-subscription v4 successor](evaluation-results/hbq-human-alignment-optimizer-v4-native-subscription-v1/)
  keeps the exact prompt bytes while naming Grok Build and Codex ChatGPT
  subscription routes honestly. The mandatory development gate is 65 Grok
  cells followed by 35 unchanged Sol validation cells; the 360-cell training
  pool is optional and confirmation remains unopened.
  The separate [development optimizer](evaluation-results/hbq-human-alignment-optimizer-v4-development-optimizer-v1/)
  can run deterministic Optuna search only over independently verified raw
  training cells and exposes a development-only DSPy program for versioned
  prompt descendants. The [lean development pilot](evaluation-results/hbq-human-alignment-optimizer-v4-lean-development-v1/)
  has exercised real Optuna `4.9.0` search and DSPy `3.3.1` descendant
  generation over independently verified persisted evidence. Both remain
  development-only: neither is imported by the scoring runtime or has runtime,
  selection, validation, or confirmation authority.
  The reviewed [lean training collector](evaluation-results/hbq-human-alignment-optimizer-v4-lean-training-exec-v1/)
  and [balanced development optimizer](evaluation-results/hbq-human-alignment-optimizer-v4-lean-development-balanced-v1/)
  now replay the retained balanced subset: 20 Grok cells across four complete
  prompt groups plus 10 sprinkled Sol cells. The entire five-candidate Grok
  group containing immutable, no-resend terminal
  `v4-cell-327fe788866eb61b` is excluded. Optuna `4.9.0` selected the existing
  `candidate-52d1be4bc34e0018` baseline (objective `1.5722222267539725`;
  Grok MAE `1.6388888889`; Sol MAE `1.3055555556`; Grok coverage `1.0`);
  none of the five current candidates improved on that baseline within this
  retained subset. The objective is `0.8 ×` Grok MAE + `0.2 ×` Sol MAE with
  only tiny additive coverage and request-byte penalties. Small-sample
  Spearman is often undefined and is not imputed or used for selection.
  The reviewed [balanced held-out evaluation](evaluation-results/hbq-human-alignment-optimizer-v4-balanced-dspy-heldout-eval-v1/)
  and [versioned executor](evaluation-results/hbq-human-alignment-optimizer-v4-balanced-dspy-heldout-exec-v1/)
  then evaluated ten DSPy descendants plus the baseline on four
  prompt-group-disjoint development groups: 44 Grok cells, followed by 22 Sol
  cells on two matched groups after Grok selection was frozen. Grok selected
  `candidate-0ca942ad28cb4104`, reducing MAE from `1.069444` to `0.875`, but
  the unchanged candidate increased Sol MAE from `1.368056` to `1.427778`.
  The endpoints are not pooled: this is a model-specific Grok development
  improvement and a Sol reversal, not independently observed cross-endpoint
  gain. Confirmation remains unopened; Grok reasoning is unattested; Sol
  proves local lifecycle only, with native endpoint/contact cardinality
  unproven; DSPy and Optuna have no runtime authority.
  The lower-edit-mass successor has nine locally reconciled Grok descendants
  and one immutable ambiguous timeout exclusion; the reviewed
  [partial reconciler](evaluation-results/hbq-human-alignment-optimizer-v4-balanced-dspy-grok-reconcile-v3/)
  grants no evaluation or selection authority. Its reviewed
  [single-sample replacement executor](evaluation-results/hbq-human-alignment-optimizer-v4-balanced-dspy-grok-exec-v4/)
  made one fresh launch, but that launch reached its 900-second postlaunch
  deadline with zero output and unknown native-contact cardinality. The root
  is an immutable ambiguous exclusion and cannot be resent; a new logical
  successor candidate is required before the ten-candidate shrinkage readout.

  All 65 [receipt-verified native Grok development cells](evaluation-results/hbq-human-alignment-optimizer-v4-native-subscription-exec-v1/) are now settled across the frozen 13-item, five-candidate development leg. Each has exactly one tool-free, zero-new-spend Grok Build subscription process launch and proven native envelope/contact, reports Grok CLI `1.0.13` and `grok-4.6-build`, requests `high` reasoning without independent attestation, and has a provider-free [admitted predecessor-shaped immutable descendant](evaluation-results/hbq-human-alignment-optimizer-v4-native-admission-v1/) with a proof file. The last twenty cells were collected in two independent ten-wide waves; all 65 native executions and all 65 admissions completed without retry. These are development observations, not an alignment or prompt-selection result.

  The provider-free [balanced partial-development readout](evaluation-results/hbq-human-alignment-optimizer-v4-development-readout-v1/)
  replays all 65 proofs and retains 15 coverage-complete cells spanning three
  items and all five candidates. It excludes 18 incomplete cells and 32 cells
  from otherwise unbalanced items. Its candidate means are descriptive only;
  the readout refuses selection, HANNA-alignment, generalization, confirmation,
  runtime, and revision-gain claims.

  The original 35-cell Sol schedule is also settled without resend: 33 [exec-v3](evaluation-results/hbq-human-alignment-optimizer-v4-native-subscription-exec-v3/) local Codex/Sol lifecycles succeeded, while the two earlier once-launched diagnostics remain immutable terminal exclusions after a Code Mode startup error and a stderr-label gate failure. Two [versioned same-group descendants](evaluation-results/hbq-human-alignment-optimizer-v4-sol-replacement-schedule-v1/) subsequently completed through the repaired [exec-v4 lifecycle](evaluation-results/hbq-human-alignment-optimizer-v4-native-subscription-exec-v4/) without rewriting or relaunching either predecessor. All successful Sol evidence preserves exact task/schema bytes and structured scores but proves only local Codex process/thread lifecycle: provider identity, reasoning, native endpoint, retry cardinality, and contact cardinality remain unproven. The [provider-free lifecycle admission](evaluation-results/hbq-human-alignment-optimizer-v4-sol-local-lifecycle-admission-v1/) preserves that ceiling as `local_lifecycle_verified_native_endpoint_contact_cardinality_unproven`. These observations do not establish Grok-as-Sol substitution, agreement, alignment, candidate selection, confirmation, or revision gain.
- The [33-pair Grok/Sol descriptive readout](evaluation-results/hbq-human-alignment-optimizer-v4-grok-sol-readout-v1/)
  reports mean absolute score difference `0.4392` across `172` covered
  pair-by-dimension observations. It is a frozen-sample discrepancy summary,
  not evidence of agreement, interchangeability, provider ranking, alignment,
  selection, generalization, confirmation, or revision gain.
- [Matched Grok/Sol calibration](evaluation-results/hbq-grok-sol-current-matched-v1/)
  is a provider-free, public-synthetic pre-execution screen. It will measure
  a narrow matched-verdict agreement question, not declare judge
  interchangeability or literary quality.
- [CWR-guided revision gain](evaluation-results/cwr-guided-revision-gain-v1/)
  remains the provider-free study design for blinded, non-CWR endpoint
  measures. The reviewed [lean v2 pilot](evaluation-results/cwr-guided-revision-gain-v2-lean-pilot/)
  and [live executor v3](evaluation-results/cwr-guided-revision-gain-v2-live-exec-v3/)
  preserve the earlier repaired schema, identity, reconciliation, and terminal
  provenance; the current endpoint result is summarized above.
- The [HANNA v5 mixed-provenance shrinkage evaluator](evaluation-results/hbq-human-alignment-optimizer-v5-balanced-dspy-mixed-provenance-shrinkage-eval-v1/)
  completed its Grok-primary development collection: 33 logical cells reduced
  to 30 unique, tool-free Grok payloads across ten effective candidates; three
  byte-identical baseline descendants remain lineage-only aliases. The
  [immutable descriptive result](evaluation-results/hbq-human-alignment-optimizer-v5-balanced-dspy-mixed-provenance-live-result-v1/)
  reports a baseline equal-group MAE of `1.1296296296296295` and a lowest
  observed candidate MAE of `0.6666666666666666` (descriptive delta
  `-0.4629629629629629`, `40.98360655737705%` relative reduction). This is
  Grok-only development evidence with native endpoint contact cardinality
  unproven: it does not select a winner or establish strict-v5 projection, Sol
  validation, confirmation, general HANNA gain, promotion, or runtime
  authority. The separate 18-lane Grok breadth wave remains provisional
  candidate generation only.
- [Flash-Next/Linux planning](evaluation-results/hbq-supplemental-providers-flash-next-v1/)
  freezes portable study geometry and an offline, non-authoritative per-root
  request journal. Native Linux execution, trusted route evidence, and pairing
  remain future work.
- [Flash-Next Linux portability diagnostic](evaluation-results/hbq-supplemental-providers-flash-next-linux-portability-v1/)
  binds the exact predecessor contract, adapter, policy, asset manifest,
  study, and adapter tests. It adds an executable provider-free plan plus a
  Linux-only, exclusive-published self-integrity diagnostic. It remains
  explicit NO-GO evidence: no native Linux run, independent attestation,
  provider/runtime provenance, pairing, or promotion is claimed.

## Install and try it

```bash
pip install "git+https://github.com/HaileyStorm/Creative-Writing-Rubrics.git"
```

From a clone, install development dependencies with `pip install -e ".[dev]"`.
HANNA prompt-development work additionally uses
`pip install -e ".[dev,hanna-dev]"`; DSPy and Optuna remain development-only.
Python 3.10+ is supported. The CLI is `cwr` (with `hbq` as an alias).

Score the included example verdicts, inspect a bundle, or render a
provider-agnostic packet:

```bash
cwr score prose.scene examples/verdicts_example.jsonl
cwr list bundles
cwr show prose.scene
cwr render-judge --bundle prose.scene --artifact examples/sample_scene.md
```

For a real judge, bring a local OpenAI-compatible endpoint:

```bash
cwr judge examples/sample_scene.md --bundle prose.scene --provider openai \
  --base-url http://127.0.0.1:8000/v1 --model local-model \
  --output-dir ../cwr-runs/sample
```

See [Running a headless judge](docs/judging.md) for Codex, Grok Build, the
Windows Nous bridge, privacy disclosure, contracts, retries, resume, and
full-fidelity long-form runs. Sampling is always explicit; omit
`--local-sample-limit` when complete local coverage is intended.

## How it works

```text
artifact + brief → validated route → frozen task contract → stable map
→ per-leaf verdicts → deterministic score → report
```

Choose a bundle, optionally freeze an artifact-bound task contract, collect
`YES`, `NO`, `NOT_APPLICABLE`, or `CANNOT_ASSESS` verdicts, and score them with
the library. Objective, explicitly non-negotiable task requirements may become
gates; author goals remain weighted questions. Open-ended review can attach
findings, but it does not rewrite scores.

For long-form work, the global result and local chapter/section diagnostics are
separate. The default is full local coverage; an explicit sample is a
diagnostic subset and is labeled as such. Reports preserve observed scores,
coverage, unresolved bounds, evidence scope, and control states rather than
collapsing them into one unsupported quality claim.

The optional GUI is an offline helper, not a server or telemetry system:

<p>
  <img src="docs/images/workflow-setup.png" width="72%" alt="Local HBQ-RS workflow setup page">
</p>

Offline reports and scorecards keep the canonical whole-work result separate
from any custom weighted composite:

<p>
  <img src="docs/images/report-overview.png" width="88%" alt="HBQ-RS offline long-form report overview">
</p>

## What is in the box

| Path | Contents |
| --- | --- |
| `registry/` | Modules, generated aggregates, question index, and criterion ownership |
| `bundles/` | Bundle presets |
| `schema/` | Module, bundle, judge-response, verdict, score-report, and review schemas |
| `prompts/judge/` | Prefix, binary, decomposition, pairwise, long-form, multimodal, and import prompts |
| `prompts/review/` | Open-ended critique families; findings do not rewrite scores |
| `src/hbqrs/` | Library and CLI |
| `docs/HBQ_RS_STANDARD.md` | Normative HBQ-RS rules |
| `docs/RUBRIC_BOOK.md` | Human-readable rubric catalog |

Technique-specific model-build modules are optional. Literary judging does not
require them.

## Results, guides, and integration

Start with the [curated results hub](docs/RESULTS.md), which groups the public
evidence by purpose and labels repeatability, full-book comparisons, negative
or no-promotion results, exploratory work, and historical packages. It also
links the detailed preface, HANNA, figurative, L2, structural-audit,
exact-repeatability, and provider-supplement records rather than flattening
every study into this front page.

- [HBQ-RS standard](docs/HBQ_RS_STANDARD.md) and [rubric catalog](docs/RUBRIC_BOOK.md)
- [Using HBQ-RS inside another application](docs/apps.md)
- [Validation and repair journey](docs/VALIDATION_AND_REPAIR_JOURNEY.md)
- [Leaf decomposition policy](docs/LEAF_DECOMPOSITION_POLICY.md)
- [Benchmarking](docs/benchmarking.md), [model training](docs/training.md), and [synthetic data](docs/synthetic-data.md)
- [Palimpsest integration handoff](docs/PALIMPSEST_HANDOFF.md), including its exact-pinned submodule and compatibility boundary

## Boundaries that matter

- Keep the selected bundle and evidence scope appropriate to the task; do not attach every module by default.
- Treat `CANNOT_ASSESS` as unresolved evidence, not as `NO`.
- Keep user taste and post-candidate preferences separate from craft requirements.
- Do not reward length, verbosity, ornament, or bland compliance by default.
- Request concise evidence, not private chain-of-thought.
- Label author-original prose and model rewrites explicitly; public case studies expose only authorized excerpts and aggregates.

Scores are structured evidence, not literary truth. Calibrate before
consequential use.

## Python API

```python
from hbqrs import compile_bundle, load_bundles, load_modules, load_verdicts
from hbqrs import resolve_bundle, score_bundle

modules = load_modules("registry/all_modules.json")
bundle = resolve_bundle(load_bundles("bundles/all_bundles.json"), "prose.scene")
packet = compile_bundle(modules, bundle)
report = score_bundle(modules, bundle, load_verdicts("examples/verdicts_example.jsonl"))
print(report["status"], report["final_score"])
```

## Verification, license, and support

Release checks cover fresh-clone and isolated-wheel installation, CLI and
Python APIs, strict schemas, local endpoint transport, public-result verifiers,
and provider-adapter/evidence-validation paths. Actual remote-execution
evidence is package-specific and explicitly labeled. The
public case studies preserve their own contracts, manifests, aggregate outputs,
and privacy checks; private manuscript prose and raw model responses are not
distributed.

This project is Apache-2.0 licensed; see [LICENSE](LICENSE) and [NOTICE](NOTICE).
Optional donations and their safety notes are documented in
[docs/DONATIONS.md](docs/DONATIONS.md).
