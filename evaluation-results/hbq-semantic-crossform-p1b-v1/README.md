# P1b cross-form AI fixture generation

This is preparation and generation of proposed synthetic fixtures, before independent AI intent review and judging. It freezes eight family requests with three variants each: four self-contained short narratives, two explicitly bounded two-scene novel/work segments, and two complete free-verse poems. Sixteen original-versus-defect/style comparisons are declared before generation. No human labels, previous private manuscripts or existing creative texts enter these prompts.

Each request supplies a fresh brief, target defect, legitimate-style control, exact variant IDs and mechanical limits, with the applicable existing canonical bundle leaf semantics. Short narratives contain 450-650 whitespace-delimited words per variant; work segments contain 900-1,200 and 50-150 words of shared generated context; poems contain 110-190 words and 18-30 nonempty lines. Descendants remain within 20% of the original's word count. These checks do not establish artistic success, realized defect intent or style/fact preservation. Poetry controls allow plausible refrain, contemplation, stillness and circular architecture; they do not require linear plotting or change on every line.

From the CWR checkout, prepare into a fresh private directory outside the repository and existing inputs:

```powershell
.\.venv\Scripts\python.exe -B evaluation-results/hbq-semantic-crossform-p1b-v1/prepare.py --secondary-helper <designated-secondary-helper.py> --codex-cli <reviewed-codex.exe> --tools-root <shared-tools-root> --output-root <fresh-private-freeze> --timeout 900 --dry-run
```

The dry run reads public canonical inputs and explicitly supplied runtime code/CLI bytes, validates the supported schema subset, prints exact prospective manifest commitments, and writes nothing. Omitting `--dry-run` creates immutable prompts, schemas, canonical input/code snapshots, selected semantics and the manifest. The preparation does not execute the CLI, import the account helper, probe an account or contact a provider. Native sampling temperature and seed are unsupported; the design ID is not a provider sampling seed. Cost, token and cache attestation are not established by this contract.

After actual freezing and the owning task's account check, run the exact frozen manifest with its printed raw-byte SHA256:

```powershell
.\.venv\Scripts\python.exe -B evaluation-results/hbq-semantic-crossform-p1b-v1/collect.py --manifest <private-freeze/manifest.json> --manifest-sha256 <raw-manifest-sha256> --results-dir <fresh-private-results> --validate-only
```

`--validate-only` performs provider-free input/code checks and replay of any accepted prefix. Omitting it enables generation solely through the designated secondary ChatGPT subscription and native Codex `gpt-6.1-sol/high`, using the existing `runner._call_codex` and `codex_native_rollout_v1` receipt policy. The standalone collector checks the pinned helper, executable, isolated home and account identity; its environment change remains in that process. The exact outbound data are the frozen fresh family briefs/intent/bounds, selected public rubric semantics and JSON response schemas. Authentication overrides are removed. Use the shared `quiet_launch.quiet_popen_options()` with argument arrays, explicit cwd and captured output when launching unattended; native Codex already uses no-window flags.

Collection uses one worker, one attempt per logical family and the frozen timeout, at most 900 seconds. Each fresh sample preserves its condition, prompt/schema, before-launch attempt marker, account commitment, raw final/events/own rollout/settings receipt, provider record, response, mechanical validation and terminal disposition. Accepted text artifacts are immutable descendants of the raw final. Resume replays accepted evidence and native receipts; every started, rejected or unadmitted slot blocks automatic resend. Failed evidence is preserved. A before-launch marker does not prove physical provider contact, and a native settings receipt does not establish backend model identity or physical-contact cardinality.

Create `<private-results>/STOP` to prevent new contacts. The collector records observing it; a currently running native call settles under its existing timeout. There is no cooperative in-flight cancellation claim. An externally interrupted started sample stays unresolved/no-resend until provider-free reconciliation. A later continuation must preserve occupied slots and existing evidence.

`accepted_generation` means structurally valid material eligible for independent blinded AI intent review. It never means accepted oracle, human label, score eligibility or promotion. The independent reviewer must assess whether the intended defect was realized and the legitimate alternative is plausible, preserve disagreements, and freeze that review before scoring. Whole-novel and performed-poetry claims are outside this bounded text generation scope.

Run the mock/provider-free behavior tests:

```powershell
.\.venv\Scripts\python.exe -B -m unittest discover -s tests -p test_semantic_fixture_generation.py
```

These tests cannot establish actual secondary-account, model, provider, cost or cache behavior. The owning task performs the actual freeze, publication, account check and generation launch.
