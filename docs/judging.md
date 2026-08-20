# Running a headless judge

`cwr judge` sends one text artifact through one compiled bundle, validates every returned verdict, checkpoints after each batch, and writes the deterministic score. It supports a local or hosted OpenAI-compatible Chat Completions endpoint and the authenticated Codex CLI.

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

`--temperature` applies only to the OpenAI-compatible backend. `--reasoning` applies only to Codex CLI; unsupported combinations fail instead of being ignored.

For model routing, a fast model is useful for broad, high-volume leaf coverage, while a stronger reasoning model is more useful for ambiguous judgments and synthesis. In the tested GPT-5.6 workflow, that means Luna Max for broad passes and Sol Medium or High for judgment and synthesis. A fake local endpoint proves transport and resume behavior, not literary judgment quality.

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

Use `--dry-run` to write the manifest and print the disclosure without contacting the provider. A dry run can later be continued with `--resume` and the same settings.

## Run directory

Keep private run directories outside a public source checkout. The chosen output directory contains:

- `run.json`: input hashes and non-secret provider settings;
- `response.schema.json`: the strict model-output contract;
- `verdicts.jsonl`: validated, resumable leaf verdicts;
- `responses/`: ordered, hash-linked batch checkpoints, exact gzip-compressed prompts, provider metadata, and normalized output;
- `score.json`: the deterministic HBQ-RS report.

The directory can contain quoted source excerpts. Treat it with the same privacy as the artifact. Nothing is uploaded by the runner except the declared artifact, declared context files, question batch, and judge instructions.

Complete score and verdict reports can be published independently of their source text. Before publishing a private evaluation, remove embedded quotes, local paths, and private run metadata while retaining verdicts, notes, references, coverage, confidence, and every score breakdown.

## Long-form work

Follow `prompts/judge/LONG_FORM_PROTOCOL.md`. Run local questions against evidence-bearing chapters or sections, retain a separate whole-work map and state ledgers, then apply global questions to those derived artifacts. Do not average chapter scores into a manuscript score. Separate comparable chapter runs from any additional full-manuscript coverage so the comparison remains interpretable.

`cwr judge` automates binary verdict collection and scoring. Task-question generation and the optional open-review prompts remain separate steps because they answer different questions and must not silently rewrite the deterministic score.
