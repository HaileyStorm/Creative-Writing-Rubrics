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
  --wip \
  --provider codex \
  --model gpt-5.6-sol \
  --structured-reasoning high \
  --judge-reasoning medium \
  --binary-workers 3 \
  --html-report \
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
  → complete-source global judging + scope-correct diagnostics for every local unit
  → deterministic score + progressive JSON/Markdown/SVG/HTML report
```

Automatic route selection is itself an LLM call through the configured endpoint. The route prompt includes the declared bounded text sample, originating prompt, and brief; the model may choose only IDs from the local catalog, and deterministic validation rejects invented IDs, incompatible scopes, new weights, or new scoring rules. The global judge receives the complete source divided into stable units, and every unit is scored independently by default. Chaptered manuscripts automatically use the unique chapter-scope bundle for local evaluation; `--local-bundle` is an explicit override for deep diagnostics. Local results never silently alter the canonical manuscript score. `--binary-workers` safely overlaps disjoint global/local run directories, up to 8 workers, without changing coverage. The final synthesis can explain the evidence but cannot change verdicts or scores.

Each scope has one canonical evaluation in a workflow. The manuscript view references the already-produced chapter result; it does not rejudge the chapter for each chart or card. If scene diagnostics are added beneath a chapter, they remain separate children rather than being averaged back into the chapter score. The parent is judged at the parent scope; smaller scopes explain where its strengths and problems occur.

`--wip` is the explicit shortcut for `--completion-status work_in_progress`. Completion-only whole-work criteria resolve as `NOT_APPLICABLE` rather than failures; evidence that should already exist inside the supplied scope can still be `CANNOT_ASSESS`, and ordinary craft, continuity, applicable requirements, and weighted goals remain active.

For constrained local hardware, `--local-sample-limit N` explicitly switches local coverage to a bounded diagnostic sample (maximum 64). The whole-work pass still receives the complete source, and the report labels the local coverage as sampled. Omit the flag for complete local coverage.

### Optional composite and offline report

The report keeps the canonical whole-work result, domain breakdown, and local trajectory as separate views. A saved hierarchical profile can add a visibly non-canonical headline without replacing any of them:

```bash
cwr init-score-profile manuscript.txt -o weights.json
cwr longform manuscript.txt --brief author-notes.txt --wip \
  --provider codex --model gpt-5.6-sol --allow-remote \
  --hierarchical-score-profile weights.json --html-report \
  --output-dir ../cwr-runs/manuscript
```

The generated starter profile uses 70% whole-work and 30% equal-weight local mean. Edit `global_weight`, `local_weight`, or choose `weakest_unit` as the local reducer. Ordinary units remain equal-weight. If needed, repeat `--unfinished-unit-ordinal` while creating the profile to apply one shared `--unfinished-unit-weight`; `--prologue-epilogue-weight` is another shared class modifier. Arbitrary per-chapter weights are intentionally unsupported.

`--html-report` writes a self-contained offline `report.html` plus a compact `scorecard.html`. The card prints the custom component weights, reducer, and active class modifiers. Render an existing strict report with `cwr render-report report.json -o report.html`; add `--scorecard` for the compact embeddable form. The browser editor previews and downloads a profile locally; it has no network calls, telemetry, storage, or server dependency.

Automatic bundle/module selection is useful for a standalone evaluation. For matched revisions, `--bundle prose.novel` freezes the complete bundle stack, `--task-contract contract.json` freezes the weighted author goals and objective requirements, and repeated `--frozen-sample-ordinal N` flags select the same one-based unit positions in each draft. A contract is artifact-bound, so give each draft a copy with its own `artifact_id`; keep every other contract field identical for a controlled comparison.

Generic OpenAI-compatible endpoints receive the strict response schema in the prompt and are validated locally. Add `--openai-structured-outputs` only when the endpoint supports OpenAI's strict JSON Schema response format; Codex uses a schema-constrained response file automatically.

Use `--driving-prompt` when the text was generated from a prompt. A brief, driving prompt, or sample text can inform route selection and weighted goals, but author taste and subjective intent are not gates. Automatic routing cannot create binding requirements; only atomic, objective, explicitly non-negotiable requirements in a user-supplied, artifact-bound `--task-contract` control eligibility.

### Multiple samples

`cwr batch` is a thin manifest wrapper around the existing runners; it does not introduce a second judging engine. A job may use `workflow: longform` (the default) for global plus multi-part diagnostics or `workflow: single` for one exact artifact score with no redundant global/local pass. One manifest may mix both. `html_report` is long-form-only; set a single job's override to `false` when the shared defaults enable it. Paths are resolved relative to the manifest file, each job has its own resumable directory, and the same explicit remote-disclosure gate applies:

```bash
cwr batch examples/batch_manifest.yaml --allow-remote
```

Choose exactly one `routing_policy`:

- `individual`: the configured LLM routes and grades every sample independently, with no confirmation pause;
- `shared`: the configured LLM chooses the stack from `shared_route_source_job_id` once, then that validated bundle/module stack is frozen across all jobs. Each artifact still receives its own bounded planning pass for scope, units, and task context before any grading begins;
- `review`: the configured LLM prepares every route first and stops. Inspect `plans/*/plan.json`, optionally add paired `approved_bundle_id` and `approved_module_ids` overrides to a job, then run the same manifest with `--accept-reviewed`.

In `review` mode, every job reaches `PLANNED` before the command returns; no grading starts during that phase. The later `--accept-reviewed` invocation revalidates the complete plan set before any grading begins, then resumes those exact plans. Pass `--resume` as well when continuing a partially graded accepted batch. The runner writes `batch.json` and a self-contained `batch-status.html`, refreshed after each durable transition. The page auto-reloads locally but has no controls that bypass the CLI, no server dependency, no upload path, and no template or theme editor. `--resume` retains the same checkpoint binding rules as the underlying runner.

The workflow directory contains public-facing `report.json`, `report.md`, `local-scores.svg`, and a concise summary; `--html-report` adds `report.html` and `scorecard.html`. Its `.private/` subtree retains source copies, prompts, maps, response checkpoints, exact evidence quotations, and the underlying score reports. Keep the entire directory private unless you deliberately sanitize an export.

`cwr judge` automates binary verdict collection and scoring. Task-question generation and the optional open-review prompts remain separate steps because they answer different questions and must not silently rewrite the deterministic score.
