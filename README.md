# Creative-Writing-Rubrics

**creative-writing-rubrics 1.1.0 · HBQ-RS 1.0.0** — composable binary-question rubrics for creative writing, draft judging, open critique, model and dataset evaluation, benchmarking, and synthetic data.

The package ships **277 modules**, **2,139 atomic leaves**, **85 bundle presets**, and deterministic scoring. A judge answers one yes/no leaf at a time; aggregation is code, not another model call.

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

`--wip` marks unfinished closure out of scope without relaxing craft, supplied-scope continuity, applicable requirements, or weighted goals. This example samples four local units; omit `--local-sample-limit` for complete local coverage. Chaptered prose uses a manuscript bundle globally and a chapter-scope bundle locally unless `--local-bundle` overrides it.

Headless judging supports Codex CLI, the optional Grok Build CLI adapter, and the Windows Nous tool-free bridge. GPT-5.6 Sol remains the primary study arm; Grok and Nous are always supplemental. When their effective reasoning is not attested, they also require explicit provisional opt-in and remain provisional evidence.

Use Sol Medium for binary batches and Sol High for routing, long-range mapping, ambiguity, and synthesis; Luna Max is for broad passes that receive stronger or deterministic review. [Running a headless judge](docs/judging.md) covers provider setup, privacy, resume, and contracts.

Automatic routing is an LLM choice from the local catalog followed by deterministic ID, compatibility, scope, and strict-schema checks. Use `--plan-only` to inspect it. For controlled draft comparisons, freeze the stack with `--bundle prose.novel`, reuse a task contract, and repeat `--frozen-sample-ordinal N` for matched positions. `--openai-structured-outputs` is optional for compatible endpoints; generic local endpoints use prompt-and-validation.

The canonical whole-work score and full chapter trajectory remain separate. For a compact headline, create an explicit profile and request the optional composite:

```bash
cwr init-score-profile manuscript.txt -o weights.json
cwr longform manuscript.txt --brief author-notes.txt --wip \
  --provider codex --model gpt-5.6-sol --allow-remote \
  --hierarchical-score-profile weights.json --html-report \
  --output-dir ../cwr-runs/manuscript
```

The default profile is 70% whole-work and 30% equal-weight local mean. Profiles can instead use the weakest-unit reducer or, with at least three local results, discard one high and one low result before averaging. Chapter weights are not individually tunable; only shared unfinished-unit and prologue/epilogue modifiers are supported. Reports label custom weights and reducers. `cwr render-report report.json -o report.html` renders offline; `--scorecard` creates an embeddable card.

The GUI is optional: setup, judging, batching, monitoring, scoring, and reports have CLI paths. `cwr configure -o setup.html` is a local, no-network helper for route, WIP, endpoint, coverage, weights, and a copyable command; it never runs a judge. There is no template editor or theme system.

<p>
  <img src="docs/images/workflow-setup.png" width="72%" alt="Local HBQ-RS workflow setup page">
</p>

The setup view is self-contained local HTML. Published study charts are derived from verified result files.

For multiple samples, `cwr batch batch.yaml --allow-remote` wraps the same runners and may mix long-form and exact single-artifact jobs. Its strict manifest chooses `individual` routing, a stack shared from one designated sample, or a planned-and-confirmed `review` route. It writes durable per-job outputs and a local status page. See [Running a headless judge](docs/judging.md).

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

Choose a local bundle (or let long-form routing choose and validate one), freeze any artifact-bound task contract, collect `YES`, `NO`, `NOT_APPLICABLE`, or `CANNOT_ASSESS` verdicts using the binary prompt, then score deterministically. Author goals are weighted questions; only atomic, objective, explicitly non-negotiable contract requirements can become gates. AI-generated or AI-modified work also receives `JUDGE_PREFIX.md`.

```text
artifact + brief → validated route → frozen task contract → stable map → per-leaf verdicts → deterministic score → report
```

For long work, global questions see the complete source; chapters or sections receive independent local results by default. `--local-sample-limit` samples up to 64 units for constrained hardware, while `--binary-workers` evaluates disjoint scopes concurrently (maximum 8). Local results never alter the canonical manuscript score; a saved profile may add a visibly custom composite. Provider or strict-output failures retry up to three times per binary batch; rejected responses remain inspectable but never enter a checkpoint or score.

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

Technique-specific model-build modules (speculation/MTP checks, pruning, refusal-behavior overlays, and similar) live under `model/` and are optional; literary judging does not require them.

Stable IDs (`module_id`, `question_id`, `bundle_id`, `criterion_key`) are the public contract. Display titles may change.

## Evidence and guides

- [Established-rubric repeatability study](evaluation-results/the-part-that-arrives-first-repeatability/established-v4/) — five GPT-5.6 Sol runs each of HBQ-RS and three research implementations derived from published rubrics
- [Authorized complete story: *The Part That Arrives First*](evaluation-results/the-part-that-arrives-first-repeatability/source.md)
- [What HBQ caught in the story](evaluation-results/the-part-that-arrives-first-repeatability/hbq-findings.md) — four concrete craft judgments, including one difficult limitation
- [Initial batching study](evaluation-results/the-part-that-arrives-first-repeatability/) — the same story under two HBQ batch shapes and two synthesized comparators
- [*Gray Blood*, chapters 1–6](evaluation-results/gray-blood-ch1-6/) — complete score and verdict reports with five authorized excerpts, clearly labeled author-original or GPT-5.6 Pro rewrite; the remaining manuscript stays private
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

Scores are structured evidence, not literary truth. Calibrate before consequential use.

## Support

This project is free. Donations are entirely optional and never affect access or support; they sustain Hailey's open-source work. You can use [Buy Me a Coffee](https://buymeacoffee.com/threadspan), or see this repository's [donation details and safety notes](docs/DONATIONS.md). No route is preferred. Never share wallet keys or provider credentials; verify recipients independently because transfers may be irreversible.

## License

Apache License 2.0. See [LICENSE](LICENSE) and [NOTICE](NOTICE). Bibliography entries identify informing papers; those works keep their own licenses.

## Verification

The release is tested from a fresh clone and isolated wheel install, through CLI and Python APIs, against strict schemas and both a fake local OpenAI-compatible endpoint and GPT-5.6 via Codex CLI. The public six-chapter case study includes publishable score breakdowns and diagnostics; the private manuscript is not distributed. Repeatability studies publish their authorized story, frozen designs, detailed outputs, and deterministic analyses.
