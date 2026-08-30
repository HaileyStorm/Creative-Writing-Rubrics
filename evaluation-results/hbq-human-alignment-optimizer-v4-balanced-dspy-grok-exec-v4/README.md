# Feedback-bound Grok descendant wave (v4)

V4 is the fresh-identity replacement for the v3 Grok wave whose native stdout used ordinary spaced JSON with CRLF. It pins v3, the v2 transport, and the exact public r4 result authority. V4 accepts strict JSON presentation while retaining and hashing the exact raw adapter stdout. Duplicate keys, non-finite numbers, malformed UTF-8, route drift, and adapter commitment drift fail closed.

`fixtures/v3-sample-01-adapter-stdout.base64` is a portable Base64 projection of the exact immutable v3 sample-01 stdout (`SHA-256 42c8b676f499ec90e9833b92ef32cd341f5479635d42df111531d58fa15f6f90`); tests decode it back to the exact spaced-JSON/CRLF bytes. The host-local immutable root is used only for the additional full preparation/route replay when present.

The adapter's request and output commitments are replayed in its actual sorted, compact UTF-8, no-trailing-LF domain. The provider's decoded instruction and profile bytes are preserved exactly. V4 also creates a separately labeled `versioned_project_canonical_profile_v1`: it repairs `instruction_sha256` to the exact raw instruction hash and serializes the derived profile as sorted compact UTF-8 with exactly one LF. The receipt records both raw and derived commitments and never describes the derived profile as unchanged provider output.

Runtime admission uses the exact nonvisual Grok adapter keyset observed in the immutable fixture. `command_identity_hash` is independently recomputed over the adapter's documented no-LF command-binding object; the exact `reasoning_attestation` literal and finite usage-telemetry schema are enforced. The adapter's `envelope_hash` names the native Grok CLI raw-stdout domain, but those native bytes are not persisted here, so V4 deliberately omits that value from validated runtime evidence and records the exclusion instead. The unmodified adapter claim remains only inside exact raw stdout and its canonical projection.

Preparation and single-sample execution retain v3's local-first disclosure, fresh route recheck, native adapter containment, one-shot terminal reconciliation, and no-resend policy. The feedback wrapper must use a new wave ID (not `r4shrink-20260830a`) while binding the pinned public authority. V4 permits only fresh replacement sample `1`; it has no batch or wave-launch surface. This package generates one raw descendant only; evaluation, selection, runtime, and confirmation authority remain absent.

Provider-free preparation for a fresh replacement wave:

```powershell
$repo = 'C:\Users\Haile\Documents\Creative-Writing-Rubrics-fresh-verify'
$executor = Join-Path $repo 'evaluation-results\hbq-human-alignment-optimizer-v4-balanced-dspy-grok-exec-v4\executor.py'
python $executor --prepare-only --output-root <fresh-v4-root> --sample-id 1 --dspy-input-preparation <pinned-preparation.json> --feedback <fresh-feedback-wrapper.json> --feedback-sha256 <sha256> --queue-root C:\Users\Haile\.codex\state\model-work-queue --authorization-acknowledgement-sha256 <ack-sha256>
```

After that one fresh root is prepared and the exact reviewed route proof remains current, execute only sample `1`:

```powershell
python $executor --execute-one --allow-remote --output-root <fresh-v4-root> --sample-id 1 --dspy-input-preparation <pinned-preparation.json> --feedback <fresh-feedback-wrapper.json> --feedback-sha256 <sha256> --queue-root C:\Users\Haile\.codex\state\model-work-queue --authorization-acknowledgement-sha256 <ack-sha256>
```

Never point V4 at a v3 root, reuse the v3 wave ID, request another sample, or resend the replacement root. V3 remains the immutable ten-sample predecessor; V4 does not repeat that wave.
