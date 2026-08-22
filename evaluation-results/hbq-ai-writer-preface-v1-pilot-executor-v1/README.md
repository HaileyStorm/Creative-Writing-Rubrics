# Experiment A pilot executor

This is the separately versioned executor for the 24-cell judge-side pilot in
`hbq-ai-writer-preface-v1`. The sealed protocol remains immutable. This package
does not implement writer-side Experiment B.

It accepts a private, already-selected four-input manifest plus a bound
`hanna-provenance-authority.json`: two items with verified `ai_written`
provenance and two with verified `non_ai_written` provenance. A separate
`matching_stratum` pairs one item from each origin level; it is not the
`source_model` field. The authority binds a deterministic private HANNA
Story/Prompt projection receipt to the exact pinned HANNA annotation CSV. Its
three annotations per `Story ID` must agree on `Prompt`, `Story`, and `Model`
before the deterministic extractor emits one `hanna_item_id=Story ID` row.
The receipt binds the original dataset hash, extraction recipe/output hash, and
provenance hash.
Executor IDs are opaque; actual origin, source model, and HANNA identifiers
remain only in private evidence.
The public work root receives only commitments, the fixed 24-cell schedule,
per-send disclosure projections, and an offline-settlement readiness record.

Each cell is one full compiled HBQ request. `current_full` uses the exact
production composition `prefix.strip() + "\n\n" + binary.strip()`
(2,644 UTF-8 bytes, SHA-256 `5498a254...bfc7e96`). The executor sends at most one
scored cell per epoch, requires an immediately preceding unscored capacity
preflight, uses two independent fresh sessions per input/arm, and stops rather
than retrying an uncertain or terminal scored send. It permits only the primary
`codex` / `gpt-5.6-sol` / `high` route.

No provider calls are made by `prepare`, `render-next-disclosure`, orphan
adjudication, or `settle-offline`. A local CLI/version/auth-channel attestation
is bound at prepare time. The no-provider `render-next-disclosure` command
renders the exact next private prompt with its safe disclosure; it never sends
the prompt. Orphan adjudication may advance only a provable zero-contact gap or
an already-complete private terminal.

```powershell
.\.venv\Scripts\python.exe -m pytest --basetemp .pytest-ai-writer-preface-pilot-executor-v1 tests/test_ai_writer_preface_pilot_executor_v1.py
.\.venv\Scripts\python.exe -m py_compile evaluation-results/hbq-ai-writer-preface-v1-pilot-executor-v1/executor.py
```
