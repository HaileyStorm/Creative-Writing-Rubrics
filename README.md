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
  --artifact-kind prose_fiction --provider openai \
  --base-url http://127.0.0.1:8000/v1 --model local-model \
  --local-sample-limit 4 --binary-workers 2 \
  --output-dir ../cwr-runs/manuscript
```

The same commands support Codex CLI. For GPT-5.6, Sol Medium is a good default for binary judging and Sol High for route selection, long-range mapping, ambiguous judgments, and synthesis. Luna Max is useful for broad passes when a stronger model or deterministic check reviews the result. See [Running a headless judge](docs/judging.md) for privacy gates, resume, task contracts, and provider details.

Automatic routing is the default. For a controlled draft comparison, add `--bundle prose.novel` to freeze the complete rubric stack, `--task-contract contract.json` to reuse the same weighted goals and objective requirements, and repeat `--frozen-sample-ordinal N` to score matched chapter positions. Endpoints that implement OpenAI Structured Outputs can opt in with `--openai-structured-outputs`; generic local endpoints remain prompt-and-validation based.

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

For long work, global questions see the complete source organized into stable units. `--local-sample-limit` bounds the representative chapters or sections that receive independent local results (maximum 64); `--binary-workers` can evaluate those disjoint scopes concurrently (maximum 8). Local results are never averaged into the manuscript score.

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

## Guides

- [Real long-form draft comparison](https://github.com/HaileyStorm/Creative-Writing-Rubrics/tree/main/evaluation-results/gray-blood-ch1-6)
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

## Verification

The release is tested from a fresh clone and isolated wheel install, through the CLI and Python APIs, against strict schemas and both a fake local OpenAI-compatible endpoint and GPT-5.6 via Codex CLI. The public six-chapter case study includes the full publishable score breakdowns and diagnostics; the private manuscript is not distributed.

## Support

This project is free. Donations are entirely optional and never affect access or support; they sustain Hailey's open-source work. You can use [Buy Me a Coffee](https://buymeacoffee.com/threadspan), or see this repository's [donation details and safety notes](docs/DONATIONS.md). No route is preferred. Never share wallet keys or provider credentials; verify recipients independently because transfers may be irreversible.

## License

Apache License 2.0. See [LICENSE](LICENSE) and [NOTICE](NOTICE). Bibliography entries identify informing papers; those works keep their own licenses.
