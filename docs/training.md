# Training and preference data

The question index is the easiest training surface:

```bash
cwr export questions --output questions.jsonl
cwr export questions --bundle prose.scene --output scene-leaves.jsonl
```

`registry/question_index.jsonl` is the same flattened leaf list for the whole book.

## Useful row shapes

**Judge SFT / trace data.** Prompt = judge prefix + one leaf + artifact excerpt. Completion = verdict JSON (`verdict`, `confidence`, `evidence`, `note`). One leaf per row. Do not train a judge to emit chain-of-thought.

**Preference pairs.** Two independently scored finalists plus an order-swapped pairwise decision. Store both HBQ reports as evidence. A `TIE` is a valid label.

**Answer-required rows.** When a preference or critique row is used, the chosen response should be substantive. A refusal or deflection may appear only as the rejected side. See `data.eval.answer_required_purity` if you are grading the dataset itself.

## Do not collapse states

Map training labels as four classes, not two:

| Verdict | Training meaning |
| --- | --- |
| `YES` | Positive criterion holds |
| `NO` | Positive criterion fails |
| `NOT_APPLICABLE` | Condition did not activate; drop from the quality total |
| `CANNOT_ASSESS` | Relevant but evidence missing; keep the interval |

Never encode `CANNOT_ASSESS` as `NO`.

## Leakage

Generate dynamic task questions from the brief only. If a judge sees candidates before the rubric is frozen, later “criteria” are just preferences about the winner. The meta-rubric `meta.dynamic_task_question_decomposition` exists to grade that process.

## Provenance

Record bundle ID, leaf ID, artifact hash, prompt file versions, provider/model, and sampler. Deterministic scores have no sampler; generative judge text does.
