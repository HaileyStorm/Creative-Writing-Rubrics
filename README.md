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

For a manuscript, `cwr longform` selects and validates a local stack, freezes declared goals, scores the whole work and local units, and can render an offline report. Binding requirements come only from an explicit `--task-contract` file:

```bash
cwr longform manuscript.txt --brief author-notes.txt \
  --artifact-kind prose_fiction --wip --provider openai \
  --base-url http://127.0.0.1:8000/v1 --model local-model \
  --local-sample-limit 4 --binary-workers 2 \
  --html-report --output-dir ../cwr-runs/manuscript
```

`--wip` marks unfinished closure as out of scope without relaxing craft, supplied-scope continuity, applicable requirements, or weighted goals. This example samples four local units; omit `--local-sample-limit` for complete local coverage. Chaptered prose uses a manuscript bundle globally and a chapter-scope bundle locally unless `--local-bundle` overrides it.

The same commands support Codex CLI, the optional Grok Build CLI adapter, and the Windows Nous tool-free bridge. For GPT-5.6, use Sol Medium for binary batches and Sol High for routing, long-range mapping, ambiguity, and synthesis; Luna Max is for broad passes that receive stronger or deterministic review. Grok 4.6 and Nous require `--allow-unattested-reasoning` when effective reasoning is not attested, so those runs are supplemental rather than exact-settings evidence. Nous accepts only `deepseek/deepseek-v4-flash-0731` or the predeclared `deepseek/deepseek-v4-pro-0813` fallback at `max`, through the shared locked zero-tool launcher; it never replaces the GPT-5.6 study arm. [Running a headless judge](docs/judging.md) covers privacy, resume, task contracts, and provider details.

Automatic routing is an LLM choice from the local catalog, followed by deterministic checks of IDs, compatibility, scope, and the strict route schema. Use `--plan-only` to inspect it. For a controlled draft comparison, freeze the stack with `--bundle prose.novel`, reuse a task contract, and repeat `--frozen-sample-ordinal N` for matched unit positions. `--openai-structured-outputs` is optional for compatible endpoints; generic local endpoints use prompt-and-validation.

The canonical whole-work score and the complete chapter trajectory are always preserved separately. If one compact headline is useful, create an explicit profile and ask for the optional composite:

```bash
cwr init-score-profile manuscript.txt -o weights.json
cwr longform manuscript.txt --brief author-notes.txt --wip \
  --provider codex --model gpt-5.6-sol --allow-remote \
  --hierarchical-score-profile weights.json --html-report \
  --output-dir ../cwr-runs/manuscript
```

The starter profile is 70% whole-work and 30% equal-weight local mean. You may change component weights, use the weakest-unit reducer, or trim one low and one high local result when at least three eligible units exist; ordinary chapters cannot be tuned individually. Only shared unfinished-unit and prologue/epilogue modifiers are available. Cards label custom weighting and print the effective weights and reducer. `cwr render-report report.json -o report.html` renders an existing report; `--scorecard` produces the embeddable card. Both work offline.

The GUI is optional: setup, judging, batching, monitoring, scoring, and reports all have complete CLI paths. `cwr configure -o setup.html` is a local, no-network helper for route, WIP, endpoint, coverage, weights, and a copyable command; it never runs a judge. There is no template editor or theme system.

<p>
  <img src="docs/images/workflow-setup.png" width="49%" alt="Local HBQ-RS workflow setup page">
  <img src="docs/images/report-overview.png" width="49%" alt="Illustrative HBQ-RS long-form report with canonical and custom-weighted scores">
</p>

Both views are self-contained local HTML. The report image uses source-free illustrative data; published study charts below are derived from verified result files.

For multiple samples, `cwr batch batch.yaml --allow-remote` wraps the same runners and may mix long-form and exact single-artifact jobs. Its strict manifest chooses `individual` routing, a stack shared from one designated sample, or a fully planned-and-confirmed `review` route. It writes durable per-job outputs and a small local status page. See [Running a headless judge](docs/judging.md).

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

Choose a local bundle (or let long-form routing choose and validate one), freeze any artifact-bound task contract, collect `YES`, `NO`, `NOT_APPLICABLE`, or `CANNOT_ASSESS` verdicts with the binary prompt, then score deterministically. Author goals are weighted questions; only atomic, objective, explicitly non-negotiable contract requirements can become gates. AI-generated or AI-modified work also receives `JUDGE_PREFIX.md`.

```text
artifact + brief → validated route → frozen task contract → stable map → per-leaf verdicts → deterministic score → report
```

For long work, global questions see the complete source; chapters or sections receive independent local results by default. `--local-sample-limit` explicitly samples up to 64 units for constrained hardware, while `--binary-workers` evaluates disjoint scopes concurrently (maximum 8). Local results never alter the canonical manuscript score; a saved profile may add a visibly custom composite. Provider or strict-output failures retry up to three times per binary batch by default; rejected responses remain inspectable but never enter a checkpoint or score.

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
