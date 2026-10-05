# Source-addressed long-form dependency pilot

`prepare.py` prepares immutable private packets without provider contact. It reads only the exact source-index-001 handoff/provenance/validation, two indexes and extracted narratives, plus their original source-fetch-001 bytes and receipts. There is no source-index manifest. Raw bytes, CRLF, Unicode characters, narrative extraction, unit/anchor coordinates and hashes remain distinct. The James narrative frame is included. The source boundary and agent annotations are mechanical/proposed evidence, not human labels or interpretation oracles.

Two contracts stay separate:

- Six dependency cases × three representations (`raw_full`, `anchored_map`, `summary_only`) × three cycles × two endpoints × one three-leaf HBQ packet and one scoped holistic arm = **216** unscored diagnostic requests. The target remains the original novella; omitted original evidence can require CANNOT_ASSESS. The 18 case-leaf instances contain 10 distinct canonical IDs. A selected-leaf result never becomes a whole-work score. Dates, documentary attribution and supernatural ontology remain uncertain where the source is uncertain.
- Two complete novellas use `prose.novella`, manuscript/complete: 175 domain leaves, one hard gate, 18 penalty leaves and 25 supplemental leaves, **219 leaves / 28 packets**. Both receive a baseline full bank; one work selected by a salted hash of work ID and original narrative hash receives cycles 1 and 2. Both receive holistic and compact judgments in all three cycles. That gives **124 requests per endpoint / 248 total**. Full banks and whole-work comparator arms receive only the exact complete narrative, with no summary/map. Canonical scoring requires all unique admitted leaves and retains gates, coverage and sensitivity bounds; this preparer computes no scores.

The total judging plan is **464** requests, plus **two separately counted source-summary generation calls**. The scoped 1–7 holistic diagnostic and whole-novella 1–7 holistic / six-dimension 1–5 compact arms are named adaptations, not newly validated human-alignment measures. Compact overall quality is an independent judgment, not an average. No pairwise arm or new creative ground truth is created. All candidate/oracle/promotion fields remain false/null.

Summary generation sees the complete original narrative and a unit-coordinate projection only. It receives no dependency cases, anchor selection, proposed maps, canonical leaves or generation-role instructions. Each summary has 650–1000 whitespace-separated words plus attribution/uncertainty notes. Mechanical admission attests lineage, source identity, bounds and schema, not factual correctness. Actual summary generation and any independent review belong to the root; missing summaries prevent a judging freeze.

The standard HBQ renderer trims trailing artifact whitespace. This named preparation uses `exact_source_body_splice_v1`: render with one collision-checked placeholder, then replace only that body with the exact source representation. The canonical renderer/questions remain unchanged. Task grounding uses exactly `json.dumps(projection, ensure_ascii=False, indent=2)` bytes, and preparation requires both those bytes and the declared representation to appear literally in every prompt. Prompt directives/rubric text are not admitted as source evidence. Existing source-policy AI assumptions are explicitly overridden for these human-authored works. No author brief, audience or canonical editorial decision is invented.

Full narrative bytes and replicated payload sizes are reported. Frozen bytes do not prove the provider received a supported full context or avoided truncation. Both famous works may be familiar to models. This two-work descriptive pilot cannot establish unseen-work generalization, human alignment or whole-novel coverage.

## Commands

Use `python -B` to avoid interpreter bytecode writes into retained inputs. Supply the exact prior P1b source-generation manifest solely for the established secondary helper/CLI/account/runtime pins; it is never supplied to summary/judging prompts. Its raw file SHA is checked independently of canonical JSON hashes. No helper import or account probe occurs during preparation.

```powershell
python -B prepare.py --source-index <source-index-001> --runtime-manifest <semantic-crossform/frozen-001/manifest.json> --prepare-summary --output-root <fresh-private-summary-freeze> --dry-run
python -B prepare.py --source-index <source-index-001> --runtime-manifest <semantic-crossform/frozen-001/manifest.json> --output-root <fresh-private-judging-freeze> --dry-run
python -B prepare.py --source-index <source-index-001> --runtime-manifest <semantic-crossform/frozen-001/manifest.json> --summary-manifest <summary-receipts.json> --output-root <fresh-private-judging-freeze> --dry-run
```

Without summaries, dry-run reports `pending_independent_source_summaries`; an actual judging freeze exits 2 and creates nothing. Successful output uses exclusive creation in a fresh directory outside the repository and every retained source/generation/result root. Actual freezing is a separate owner action; these commands do not authorize judging, target opening or provider execution.

## Summary collector handoff

The summary generation manifest freezes exactly two Sol requests, with original narrative/complete source-index commitments, prospective source-only prompts and response schemas. A future collector must keep one attempt per logical request, exact secondary account binding, own native receipt verification, and no ambiguous resend. Its root `job.json` must equal `summary_job_binding(manifest, raw_manifest_sha256)`, and `account-binding.json` must equal the existing generation adapter's `expected_account_binding(manifest)`. Add the collector's own immutable dispatch/code commitment separately before contact; this preparer does not provide a collector or live route gate.

Each sample preserves `condition.json`, `attempt-started.json`, `prompt.txt`, `schema.json`, `native-result.json`, `response.json`, `validation.json`, exact derived `summary.txt`, and own native provider artifacts. `validation.json` equals `validate_summary(...)`. The terminal uses `state=accepted_generation`, `no_resend=true`, exact `manifest_sha256` and `logical_sample_id`, each `<record-name>_sha256` for condition/attempt-started/native-result/response/validation, and `derived_summary={path,sha256,bytes}`. Attempt-started binds the same manifest/logical ID, prompt/schema hashes, `attempt=1`, `no_resend=true`, and raw account-binding hash. These follow the established native receipt structure; no P1b family/variant roles are relabeled as summaries.

The owner-supplied receipt wrapper has this exact shape (paths resolve relative to the wrapper):

```json
{"schema_version":1,"policy":"longform_source_summary_receipts_v1","generation_manifest":{"path":"summary-frozen/manifest.json","sha256":"RAW_FILE_SHA256"},"summaries":[{"work_id":"pg43","logical_sample_id":"FROZEN_REQUEST_ID","sample_path":"summary-results/0001-ID"},{"work_id":"pg209","logical_sample_id":"FROZEN_REQUEST_ID","sample_path":"summary-results/0002-ID"}]}
```

Judging preparation replays both source-to-summary native receipts, unique own native thread IDs, account/prompt/schema/condition/terminal commitments and derived text. It preserves this private lineage and original artifacts. Grok route/account/model/deadline admission and native context-delivery evidence remain required before any later dispatch. No provider launch, retries, labels, scoring promotion or analysis is implemented here.
