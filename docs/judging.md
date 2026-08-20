# Running a headless judge

`cwr judge` sends one text artifact through one compiled bundle, validates every returned verdict, checkpoints after each batch, and writes the deterministic score. It supports a local or hosted OpenAI-compatible Chat Completions endpoint and the authenticated Codex CLI. A frozen task contract can add weighted author goals and objective binding requirements without mixing the two.

## Local OpenAI-compatible endpoint

```bash
cwr judge draft.txt \
  --bundle prose.scene \
  --provider openai \
  --base-url http://127.0.0.1:8000/v1 \
  --model local-model \
  --output-dir ../cwr-runs/draft-scene
```

The endpoint may be a llama.cpp server, LM Studio, Ollama's OpenAI-compatible API, or another service that accepts `POST /v1/chat/completions`. Set the API key in an environment variable and name it with `--api-key-env`; the runner never writes its value. The endpoint must report the effective model it used. If a server returns a known canonical alias instead of the requested name, review that mapping and pass `--allow-model-mismatch` explicitly.

For a non-loopback URL, the runner prints the destination plus each input's path, byte count, and SHA-256 hash, then requires `--allow-remote`.

## Codex CLI

```bash
cwr judge draft.txt \
  --bundle prose.scene \
  --provider codex \
  --model gpt-5.6-sol \
  --reasoning medium \
  --allow-remote \
  --output-dir ../cwr-runs/draft-scene-sol
```

Codex runs ephemerally with user configuration, project rules, shell, agents, apps, browsing, computer use, image tools, skills, and tool suggestions disabled. It receives the artifact through standard input and must return a response matching `schema/hbq_judge_response.schema.json`; the reported OpenAI provider, model, and reasoning effort must match the request. Use `--context brief.txt` for a brief, canon note, or other declared evidence; the option is repeatable. Use `--strict-ai` when the artifact was AI-generated or AI-modified and the stricter judge prefix is appropriate.

Use `--task-contract contract.json` when a brief should affect scoring or eligibility. The file must match `schema/hbq_task_contract.schema.json`. `weighted_goals` affect the task-domain score; only atomic, objective, explicitly non-negotiable `binding_requirements` become hard gates. Context, preferences, aspirations, and inferred author intent are never silently promoted into gates. The same contract can be supplied to `cwr compile`, `cwr render-judge`, and `cwr score`.

`--temperature` applies only to the OpenAI-compatible backend. `--reasoning` applies only to Codex CLI; unsupported combinations fail instead of being ignored.

For model routing, use the smallest reasoning level that still handles the evidence reliably. In the current GPT-5.6 workflow, Sol Medium is the default for structured binary batches and Sol High is reserved for route selection, long-range mapping, ambiguous judgments, and synthesis. Luna Max remains a reasonable high-volume broad-pass option when a stronger deterministic or Sol review follows. A fake local endpoint proves transport and resume behavior, not literary judgment quality.

## Batches, subsets, and resume

The default batch contains 12 independent leaves. Increase `--batch-size` to reduce repeated context on a capable model, or lower it when an endpoint has a small context/output limit. To smoke-test or investigate a subset, repeat `--question-id`:

```bash
cwr judge draft.txt \
  --bundle prose.scene \
  --provider openai \
  --model local-model \
  --question-id craft.narrative.scene_construction.purpose \
  --output-dir ../cwr-runs/smoke
```

If a run stops after a completed batch, repeat the same command with `--resume`. Resume fails closed if the artifact, context, prompts, bundle, question selection, model, or provider settings changed.

A selected-question run writes `diagnostic.json` with status `DIAGNOSTIC_SUBSET`; it does not write `score.json`. This prevents a smoke test or chapter-local selection from masquerading as a complete bundle score. Keep and compare the individual verdicts; never average diagnostic subsets.

Use `--dry-run` to write the manifest and print the disclosure without contacting the provider. A dry run can later be continued with `--resume` and the same settings.

## Run directory

Keep private run directories outside a public source checkout. The chosen output directory contains:

- `run.json`: input hashes and non-secret provider settings;
- `response.schema.json`: the strict model-output contract;
- `verdicts.jsonl`: validated, resumable leaf verdicts;
- `responses/`: ordered, hash-linked batch checkpoints, exact gzip-compressed prompts, provider metadata, and normalized output;
- `score.json`: the deterministic HBQ-RS report for a complete bundle; or
- `diagnostic.json`: verdict counts and selection metadata for a selected-question run.

The directory can contain quoted source excerpts. Treat it with the same privacy as the artifact. Nothing is uploaded by the runner except the declared artifact, declared context files, question batch, and judge instructions.

Complete score and verdict reports can be published independently of their source text. Before publishing a private evaluation, remove embedded quotes, local paths, and private run metadata while retaining verdicts, notes, references, coverage, confidence, and every score breakdown.

## Long-form work

`cwr longform` automates the protocol while keeping every phase inspectable and resumable:

```bash
cwr longform manuscript.txt \
  --brief author-notes.txt \
  --artifact-kind prose_fiction \
  --scope manuscript \
  --completion-status work_in_progress \
  --provider codex \
  --model gpt-5.6-sol \
  --structured-reasoning high \
  --judge-reasoning medium \
  --local-sample-limit 4 \
  --binary-workers 3 \
  --allow-remote \
  --output-dir ../cwr-runs/manuscript
```

The flow is:

```text
artifact + brief
  → locally constrained bundle/module selection
  → frozen weighted goals and, when user-supplied, explicit binding requirements
  → deterministic source-preserving segmentation
  → whole-work map and state ledgers
  → complete-source global judging + independent sampled-unit diagnostics
  → deterministic score + narrative JSON/Markdown/SVG report
```

Route selection can choose only IDs from the local catalog; it cannot invent rubric leaves, weights, or scoring rules. The global judge receives the complete source divided into stable units. `--local-sample-limit` gives route selection a hard ceiling of 64 representative local units. Each selected unit is scored independently for diagnosis, and those results are never averaged into the manuscript score. `--binary-workers` safely overlaps disjoint global/local run directories, up to 8 workers; keep it modest for endpoint limits. The final synthesis can explain the evidence but cannot change verdicts or scores.

Automatic bundle/module selection is useful for a standalone evaluation. For matched revisions, `--bundle prose.novel` freezes the complete bundle stack, `--task-contract contract.json` freezes the weighted author goals and objective requirements, and repeated `--frozen-sample-ordinal N` flags select the same one-based unit positions in each draft. A contract is artifact-bound, so give each draft a copy with its own `artifact_id`; keep every other contract field identical for a controlled comparison.

Generic OpenAI-compatible endpoints receive the strict response schema in the prompt and are validated locally. Add `--openai-structured-outputs` only when the endpoint supports OpenAI's strict JSON Schema response format; Codex uses a schema-constrained response file automatically.

Use `--driving-prompt` when the text was generated from a prompt. A brief, driving prompt, or sample text can inform route selection and weighted goals, but author taste and subjective intent are not gates. Automatic routing cannot create binding requirements; only atomic, objective, explicitly non-negotiable requirements in a user-supplied, artifact-bound `--task-contract` control eligibility.

The workflow directory contains public-facing `report.json`, `report.md`, `local-scores.svg`, and a concise summary. Its `.private/` subtree retains source copies, prompts, maps, response checkpoints, exact evidence quotations, and the underlying score reports. Keep the entire directory private unless you deliberately sanitize an export.

`cwr judge` automates binary verdict collection and scoring. Task-question generation and the optional open-review prompts remain separate steps because they answer different questions and must not silently rewrite the deterministic score.
