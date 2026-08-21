# Ox Alpha provisional HANNA pilot

This package freezes an outcome-blind, three-story supplemental comparison. GPT-5.6 is still the primary condition. Ox Alpha uses the canonical Nous tool-free judge bridge with `stealth/ox-alpha`, requested `max`, exactly 178 questions per story, batch size 32, six serial batches per story, one attempt per batch, and no more than 18 logical requests.

Preparation records only primary input and GPT public-output hashes; it does not parse scores. Run data, requests, responses, and bridge evidence belong in an external private work root, never this repository.

```powershell
$env:PYTHONPATH='src'
.\.venv\Scripts\python.exe evaluation-results\hbq-human-alignment-supplemental-providers-ox-alpha-v1\prepare_pilot.py --primary-work-dir <primary-work> --gpt-output-dir <public-gpt-development-output> --zero-cost-proof <sealed-nous-catalog-usage-proof> --work-dir <private-ox-work>
.\.venv\Scripts\python.exe evaluation-results\hbq-human-alignment-supplemental-providers-ox-alpha-v1\run_pilot.py --work-dir <private-ox-work>
.\.venv\Scripts\python.exe evaluation-results\hbq-human-alignment-supplemental-providers-ox-alpha-v1\analyze_pilot.py --work-dir <private-ox-work> --output-dir <new-public-output>
```

Preparation accepts only a private `codex-nous-ox-alpha-zero-cost-proof-v3` file naming two distinct externally sealed EvidenceRoots: a catalog root and an Ox usage root. The canonical bridge validator must authenticate both roots. The catalog's raw `/models` response must contain exactly one `stealth/ox-alpha` record with zero prompt and completion pricing; the usage root's raw successful HTTP response must report `stealth/ox-alpha`, zero usage cost, zero structured cost details, and no structured charge/payment signal. Preparation records those immutable bytes and its then-current freshness decision; later replay verifies the frozen bytes and original decision without expiring completed evidence. The remote destination and sent artifacts are declared in `study-contract.json`. The bridge has an internal ceiling of two physical HTTP attempts per logical request (36 for this pilot); any recovered request or non-2xx event freezes the root and excludes the run. Stop permanently on any charge signal or HTTP 402, invalid or unshared-EvidenceRoot proof, model/schema/runtime/input drift, receipt reuse, private content, or failed cell. Missing provider `max` attestation is expected, but makes all evidence provisional. This pilot is never an exact gate, promotion, replacement, or human-alignment claim.
