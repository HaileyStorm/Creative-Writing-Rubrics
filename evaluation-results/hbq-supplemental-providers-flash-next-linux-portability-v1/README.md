# Flash-Next Linux diagnostic gate

This versioned successor binds the exact Flash-Next v1 contract, adapter, policy, asset manifest, study, and adapter tests. It is provider-free and has no route, model, network, dispatch, acceptance, pairing, or billing capability.

`plan` runs on any host and is explicitly `NO_GO_PROVIDER_FREE_PORTABILITY_PLAN`. It validates the frozen predecessor bindings but cannot establish Linux execution.

`verify EVIDENCE_ROOT` is Linux-only. `EVIDENCE_ROOT` must be a new caller-supplied directory outside this repository with no symlink or reparse ancestor. It creates that root exclusively, captures a no-follow directory identity, then uses exact in-memory bytes of the bound v1 adapter to exercise its POSIX publication implementation: no-follow directory handles, exclusive creation, atomic replacement, containing-directory fsync, pre-existing-target refusal, and symlink refusal. It records an exclusive-published diagnostic with platform, architecture, Python executable/path/hash/version, filesystem/device facts, predecessor and successor source hashes, command, and checks.

The resulting artifact is `exclusive_published_self_integrity_linux_diagnostic`, with state `NO_GO_NATIVE_PORTABILITY_OR_PROMOTION`. Its unkeyed self-digest only detects ordinary byte drift; `validate-evidence` checks schema and self-integrity, never host provenance or native execution. A fabricated but self-consistent record remains non-provenance diagnostic data, not native proof.

No existing evidence root may be resumed or overwritten. Unsupported operating-system, filesystem, or POSIX primitive semantics fail closed before a diagnostic record. The package has no network, provider, dispatch, model, or billing implementation and records no such observed action; this is not a sandbox-enforcement claim.

Residual gaps remain explicit: ancestor/root TOCTOU absence is not proven, the diagnostic does not independently attest native Linux execution or filesystem semantics, and no external attestation or model/runtime/pairing/promotion evidence exists.

Provider-free planning check:

```powershell
.\.venv\Scripts\python.exe evaluation-results\hbq-supplemental-providers-flash-next-linux-portability-v1\preflight.py plan
.\.venv\Scripts\python.exe -m pytest -q tests\test_hbq_flash_next_linux_portability_v1.py
```

Native Linux only:

```sh
python3 evaluation-results/hbq-supplemental-providers-flash-next-linux-portability-v1/preflight.py verify /absolute/new/external/evidence-root
python3 evaluation-results/hbq-supplemental-providers-flash-next-linux-portability-v1/preflight.py validate-evidence /absolute/new/external/evidence-root
```
