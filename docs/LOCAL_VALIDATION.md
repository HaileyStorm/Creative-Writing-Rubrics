# Local acceptance

There is no routine unit or integration suite. Ordinary pytest discovery is
disabled, and pytest is no longer a development dependency. The old `core`,
`registry`, `package`, `publications` and `--study` runner lanes are retired.
Do not replace them with a renamed scenario matrix or require a test count.

When a change affects local execution, exercise the affected shipped command
once. This optional, provider-free CLI journey compiles a real bundle, renders
its prompt for the included scene, and scores the included historical verdicts:

```powershell
$acceptanceDir = Join-Path $env:TEMP ("cwr-acceptance-" + [guid]::NewGuid())
New-Item -ItemType Directory -Path $acceptanceDir | Out-Null
.venv\Scripts\python.exe -m hbqrs compile prose.scene -o "$acceptanceDir\packet.json"
.venv\Scripts\python.exe -m hbqrs render-judge --bundle prose.scene --artifact examples/sample_scene.md -o "$acceptanceDir\judge.md"
.venv\Scripts\python.exe -m hbqrs score prose.scene examples/verdicts_example.jsonl --admission-policy historical_permissive_v1 -o "$acceptanceDir\score.json"
```

Inspect the relevant output for the changed behavior. This exercises the actual
local application and its included example; it does not establish strict-import,
provider, resume, human-alignment or every scoring-boundary behavior. Obtain
additional actual evidence only for an unresolved claim affected by the change.
Do not rerun this journey for documentation-only changes.

For authored registry changes, `python -m hbqrs pack` rebuilds the production
aggregates and `python -m hbqrs validate` applies the runtime schema validator.
There is no additional count/parity/all-bundle test sweep. Build and inspect the
distribution when packaging inputs change or a release is being prepared;
ordinary edits do not require a package build or a publication hash sweep.

The removed default smoke suites tested hard-coded release/inventory values
and a synthetic loopback provider. The CLI journey makes no claim to replace
their individual assertions. Runtime ownership, stop, no-resend, resource,
schema, semantic admission and frozen-source controls remain in production.
Research eligibility and prospective evidence requirements remain unchanged.

Retained study modules, fixtures and public-result verifiers are dormant
historical/provenance support. Reproduce a named obligation from its recorded
source and environment, with an explicitly installed historical test runner
if required. Current ordinary discovery is not historical reproduction.
`artifact-receipts/pytest-regenerable-output.v1.json` and
`artifact-receipts/large-final-regenerable-output.v1.json` retain their original
BLOCKED full-replacement obligations at source `e363d645`; this cleanup neither
runs nor settles those gates. Other frozen inputs, receipts, source hashes and
formal or scientific claims are unchanged. Previously uncommitted publication
test cleanup remains separate from this audit.
