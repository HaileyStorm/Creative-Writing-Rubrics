# Creative-Writing-Rubrics

**HBQ-RS 1.0.0** — a composable stack of binary-question rubrics for creative writing, draft judging, open critique, model/dataset evaluation, benchmarking, and synthetic data.

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

1. Pick a **bundle** for the artifact and operation (`prose.scene`, `poetry.sonnet.shakespearean`, `default.first_pass_screening`, …).
2. Optionally generate ephemeral hard/task questions from the brief with `prompts/judge/TASK_DECOMPOSITION_PROMPT.md` *before* candidates are visible.
3. Ask each selected leaf with `prompts/judge/JUDGE_PREFIX.md` + `BINARY_EVALUATION_PROMPT.md`.
4. Collect JSONL verdicts: `YES`, `NO`, `NOT_APPLICABLE`, or `CANNOT_ASSESS`.
5. Run `cwr score`. Hard gates decide eligibility; scored leaves decide quality; penalties are capped; missing evidence widens an interval instead of counting as failure.

```text
brief → task questions → compiled bundle → per-leaf verdicts → deterministic score → optional open review
```

Do not average chapter scores into a manuscript score. Use `prompts/judge/LONG_FORM_PROTOCOL.md`.

## What is in the box

| Path | Contents |
| --- | --- |
| `registry/` | Modules (YAML + JSON/JSONL aggregates), question index, criterion ownership |
| `bundles/` | 100-point presets |
| `schema/` | JSON Schemas for modules, bundles, verdicts, score reports, open review |
| `prompts/judge/` | Prefix, binary eval, task decomposition, pairwise, long-form, multimodal, import validation |
| `prompts/review/` | Open-ended critique families (findings only; they do not rewrite scores) |
| `docs/HBQ_RS_STANDARD.md` | Normative scoring rules |
| `docs/RUBRIC_BOOK.md` | Human-readable catalog |
| `src/hbqrs/` | Library + CLI |

Technique-specific model-build modules (speculation/MTP checks, pruning, refusal-behavior overlays, and similar) live under `model/` and are optional. Literary judging does not require them.

Stable IDs (`module_id`, `question_id`, `bundle_id`, `criterion_key`) are the public contract. Display titles may change.

## Guides

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

## License

Apache License 2.0. See [LICENSE](LICENSE) and [NOTICE](NOTICE). Bibliography entries identify informing papers; those works keep their own licenses.
