# Creative-Writing-Rubrics

**HBQ-RS 1.0.0** — a composable stack of binary-question rubrics for creative writing, draft judging, open critique, model/dataset evaluation, benchmarking, and synthetic data.

The package ships **277 modules**, **2,139 atomic leaves**, and **85 bundle presets**, plus deterministic scoring. A judge answers one yes/no leaf at a time. Aggregation is code, not another model call.

## Verification status

Fresh-clone installation, CLI and Python workflows, wheel contents, schemas, and examples have been verified. The headless runner is tested against a local endpoint and GPT-5.6. This public repository includes a real two-draft, six-chapter evaluation with 778 quote-free verdicts and 14 score reports, plus a separate 249-verdict extension over all seven available chapters of the original draft. The private manuscript is not published.

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

The same command supports Codex CLI. Local fake-endpoint tests cover transport; for real GPT-5.6 evaluation, Luna Max suits broad passes and Sol Medium/High suits judgment and synthesis. See [Running a headless judge](docs/judging.md) for privacy gates, resume, context files, and long-form use.

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
2. Optionally generate ephemeral hard/task questions from the brief with `prompts/judge/TASK_DECOMPOSITION_PROMPT.md` *before* candidates are visible. This begins the LLM-as-judge phase; the final score is still aggregated deterministically.
3. Ask each selected leaf with `BINARY_EVALUATION_PROMPT.md`; add `JUDGE_PREFIX.md` when the artifact is AI-generated or AI-modified.
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
- [Full-original chapters 1-7 extension](https://github.com/HaileyStorm/Creative-Writing-Rubrics/tree/main/evaluation-results/gray-blood-original-ch1-7)
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
