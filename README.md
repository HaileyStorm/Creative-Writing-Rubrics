# Creative-Writing-Rubrics

**creative-writing-rubrics 1.1.0 · HBQ-RS 1.0.0** — a composable stack of binary-question rubrics for creative writing, draft judging, open critique, model/dataset evaluation, benchmarking, and synthetic data.

The package ships **277 modules**, **2,139 atomic leaves**, and **85 bundle presets**, plus deterministic scoring. A judge answers one yes/no leaf at a time. Aggregation is code, not another model call.

## Install

```bash
pip install "git+https://github.com/HaileyStorm/Creative-Writing-Rubrics.git"
```

From a clone:

```bash
pip install -e ".[dev]"
```

Requires Python 3.10+. The CLI is `cwr` (alias `hbq`).

## 30-second start

Score the included example verdicts:

```bash
cwr score prose.scene examples/verdicts_example.jsonl
```

List presets, inspect one, compile a judge packet:

```bash
cwr list bundles
cwr show prose.scene
cwr compile prose.scene -o /tmp/scene-packet.json
```

Render a provider-agnostic judge prompt (bring your own model):

```bash
cwr render-judge --bundle prose.scene --artifact examples/sample_scene.md
```

Or run and score a headless judge through a local OpenAI-compatible endpoint:

```bash
cwr judge examples/sample_scene.md --bundle prose.scene --provider openai \
  --base-url http://127.0.0.1:8000/v1 --model local-model --output-dir ../cwr-runs/sample
```

For a manuscript, `cwr longform` can select a valid bundle/module stack, turn a brief into frozen weighted goals, segment and map the work, run whole-work scoring plus independent local diagnostics, and render a narrative report. Binding requirements come only from an explicit `--task-contract` file:

```bash
cwr longform manuscript.txt --brief author-notes.txt \
  --artifact-kind prose_fiction --wip --provider openai \
  --base-url http://127.0.0.1:8000/v1 --model local-model \
  --local-sample-limit 4 --binary-workers 2 \
  --html-report --output-dir ../cwr-runs/manuscript
```

`--wip` makes the completion policy explicit: absent future closure or payoff is not a failure, while craft, supplied-scope continuity, applicable requirements, and weighted goals remain active. The local-endpoint example explicitly samples four units. Omit `--local-sample-limit` for the default complete mode, which evaluates every deterministic chapter or section locally as well as the whole work. For chaptered prose, the whole-work pass uses the manuscript bundle while chapter diagnostics automatically use the chapter-scope bundle; pass `--local-bundle` only when you deliberately want a different deep-diagnostic stack.

The same commands support Codex CLI, the optional Grok Build CLI adapter, and the Windows Nous tool-free bridge. For GPT-5.6, Sol Medium is a good default for binary judging and Sol High for route selection, long-range mapping, ambiguous judgments, and synthesis. Luna Max is useful for broad passes when a stronger model or deterministic check reviews the result. Grok 4.6 and Nous require explicit `--allow-unattested-reasoning` when their providers cannot attest effective reasoning; those opted-in runs are supplemental rather than exact-settings evidence. Nous accepts only `deepseek/deepseek-v4-flash-0731` or the predeclared `deepseek/deepseek-v4-pro-0813` fallback at `max`, uses the shared locked zero-tool launcher, and never replaces the GPT-5.6 study arm. See [Running a headless judge](docs/judging.md) for privacy gates, resume, task contracts, and provider details.

Automatic routing is an LLM pass through the configured endpoint, not a filename or browser heuristic. The model sees the declared sample, prompt, and brief, chooses only from the local bundle/module catalog, and the runner then enforces IDs, compatibility, scope, and the strict route schema deterministically. Add `--plan-only` to inspect that choice before judging. For a controlled draft comparison, add `--bundle prose.novel` to freeze the complete rubric stack, `--task-contract contract.json` to reuse the same weighted goals and objective requirements, and repeat `--frozen-sample-ordinal N` to score matched chapter positions. Endpoints that implement OpenAI Structured Outputs can opt in with `--openai-structured-outputs`; generic local endpoints remain prompt-and-validation based.

The canonical whole-work score and the complete chapter trajectory are always preserved separately. If one compact headline is useful, create an explicit profile and ask for the optional composite:

```bash
cwr init-score-profile manuscript.txt -o weights.json
cwr longform manuscript.txt --brief author-notes.txt --wip \
  --provider codex --model gpt-5.6-sol --allow-remote \
  --hierarchical-score-profile weights.json --html-report \
  --output-dir ../cwr-runs/manuscript
```

The starter profile is 70% whole-work and 30% equal-weight local mean. You can change those component weights or use the weakest-unit reducer. Ordinary chapters cannot be tuned one by one: the only local modifiers are one shared weight for explicitly unfinished units and an optional shared prologue/epilogue weight. The compact card labels custom weighting and prints the effective weights and reducer. Existing report JSON can be rendered later with `cwr render-report report.json -o report.html`, or with `--scorecard` for the embeddable card alone; both files are self-contained and work offline.

The GUI is always optional; every setup, judging, batching, monitoring, scoring, and report operation has a complete CLI path. `cwr configure -o setup.html` creates a local setup helper for automatic or manual stack selection, WIP/completion policy, endpoint settings, coverage, weights, and a copyable command. It never runs a judge. There is no template editor or theme system.

<p>
  <img src="docs/images/workflow-setup.png" width="49%" alt="Local HBQ-RS workflow setup page">
  <img src="docs/images/report-overview.png" width="49%" alt="Illustrative HBQ-RS long-form report with canonical and custom-weighted scores">
</p>

Both views are self-contained local HTML. The report image uses source-free illustrative data; published study charts below are derived from verified result files.

For multiple samples, `cwr batch batch.yaml --allow-remote` wraps the same runners and may mix `longform` jobs with exact single-artifact jobs. A strict manifest chooses one routing policy: `individual` lets the endpoint route and grade each sample without confirmation; `shared` chooses a stack from one designated sample, freezes it, then plans each artifact before grading; `review` finishes every sample's route plan up front, then `--accept-reviewed` revalidates the full set and grades the accepted or explicitly overridden plans. The batch writes durable per-job outputs plus a small local auto-refreshing status page. See [Running a headless judge](docs/judging.md).

Python:

```python
from hbqrs import compile_bundle, load_bundles, load_modules, load_verdicts, resolve_bundle, score_bundle

modules = load_modules("registry/all_modules.json")
bundle = resolve_bundle(load_bundles("bundles/all_bundles.json"), "prose.scene")
packet = compile_bundle(modules, bundle)
report = score_bundle(modules, bundle, load_verdicts("examples/verdicts_example.jsonl"))
print(report["status"], report["final_score"])
```

## How judging works

1. Pick a **bundle** for the artifact and operation (`prose.scene`, `poetry.sonnet.shakespearean`, `default.first_pass_screening`, …), or let the long-form runner select a valid stack from the local catalog.
2. Freeze the task contract before judging. Author goals and preferences become weighted questions; only atomic, objective, explicitly non-negotiable requirements supplied in an artifact-bound contract can become gates. Automatic routing cannot create them.
3. Ask each selected leaf with `BINARY_EVALUATION_PROMPT.md`. **This is the LLM-as-judge part.** Add `JUDGE_PREFIX.md` when the artifact is AI-generated or AI-modified.
4. Collect JSONL verdicts: `YES`, `NO`, `NOT_APPLICABLE`, or `CANNOT_ASSESS`.
5. Run `cwr score`. Hard gates decide eligibility; scored leaves decide quality; penalties are capped; missing evidence widens an interval instead of counting as failure.

```text
artifact + brief → validated route → frozen task contract → stable map → per-leaf verdicts → deterministic score → report
```

For long work, global questions see the complete source organized into stable units and every chapter or section receives an independent local result by default. `--local-sample-limit` is an explicit sampled mode for constrained local hardware (maximum 64); `--binary-workers` can evaluate disjoint scopes concurrently (maximum 8) without changing coverage. Local results never silently alter the canonical manuscript score. An optional, visibly custom-weighted composite may combine the preserved whole-work and local views under a saved profile.

Provider or strict-output failures are retried up to three times per binary batch by default. Each rejected response is retained separately for inspection and never enters a verdict checkpoint or score; use `--batch-attempts` to choose a different positive bound.

## What is in the box

| Path | Contents |
| --- | --- |
| `registry/` | Modules (YAML + JSON/JSONL aggregates), question index, criterion ownership |
| `bundles/` | 100-point presets |
| `schema/` | JSON Schemas for modules, bundles, strict judge responses, verdicts, score reports, open review |
| `prompts/judge/` | Prefix, binary eval, task decomposition, pairwise, long-form, multimodal, import validation |
| `prompts/review/` | Open-ended critique families (findings only; they do not rewrite scores) |
| `docs/HBQ_RS_STANDARD.md` | Normative scoring rules |
| `docs/RUBRIC_BOOK.md` | Human-readable catalog |
| `src/hbqrs/` | Library + CLI |

Technique-specific model-build modules (speculation/MTP checks, pruning, refusal-behavior overlays, and similar) live under `model/` and are optional. Literary judging does not require them.

Stable IDs (`module_id`, `question_id`, `bundle_id`, `criterion_key`) are the public contract. Display titles may change.

## Evidence and guides

- [Established-rubric repeatability study](evaluation-results/the-part-that-arrives-first-repeatability/established-v4/) — five GPT-5.6 Sol runs each of HBQ-RS and three research implementations derived from published rubrics
- [Authorized complete story: *The Part That Arrives First*](evaluation-results/the-part-that-arrives-first-repeatability/source.md)
- [What HBQ caught in the story](evaluation-results/the-part-that-arrives-first-repeatability/hbq-findings.md) — four concrete craft judgments, including one difficult limitation
- [Initial batching study](evaluation-results/the-part-that-arrives-first-repeatability/) — the same story under two HBQ batch shapes and two synthesized comparators
- [Gray Blood chapters 1–6](evaluation-results/gray-blood-ch1-6/) — complete sanitized scoring and verdict data for a private long-form WIP comparison
- [Run a headless judge](docs/judging.md)
- [Embed in another app](docs/apps.md)
- [Benchmarking](docs/benchmarking.md)
- [Model training](docs/training.md)
- [Synthetic data](docs/synthetic-data.md)
- [HBQ-RS standard](docs/HBQ_RS_STANDARD.md)

## Design cautions

- Do not attach every module to every task.
- Do not treat `CANNOT_ASSESS` as `NO`.
- Do not mix user taste into craft scores.
- Do not reward length, verbosity, ornament, or bland compliance by default.
- Do not penalize an explicitly flagged excerpt for being incomplete.
- Do not request private chain-of-thought; request concise evidence.
- Do not let a judge invent new artistic preferences after seeing candidates.

Scores are structured evidence, not literary truth. Calibrate before high-stakes use.

## Support

This project is free. Donations are entirely optional and never affect access or support; they sustain Hailey's open-source work. You can use [Buy Me a Coffee](https://buymeacoffee.com/threadspan), or see this repository's [donation details and safety notes](docs/DONATIONS.md). No route is preferred. Never share wallet keys or provider credentials; verify recipients independently because transfers may be irreversible.

## License

Apache License 2.0. See [LICENSE](LICENSE) and [NOTICE](NOTICE). Bibliography entries identify informing papers; those works keep their own licenses.

## Verification

The release is tested from a fresh clone and isolated wheel install, through the CLI and Python APIs, against strict schemas and both a fake local OpenAI-compatible endpoint and GPT-5.6 via Codex CLI. The public six-chapter case study includes the full publishable score breakdowns and diagnostics; the private manuscript is not distributed. The repeatability studies publish their authorized story, frozen designs, detailed outputs, and deterministic analyses.
