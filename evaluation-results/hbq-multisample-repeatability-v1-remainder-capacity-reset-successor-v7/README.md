# HBQ multisample repeatability v1: V7 continuation

V7 is a separate, fail-closed descendant of the V6 live root. It never resumes, changes, recovers, or deletes V6 state.

V6 independently completed sequences 179 and 180 with one persisted provider contact each. Sequence 181 stopped after V6 had written its intent and claim, but before its runner could invoke `before_provider_attempt` or `_call_codex`. V7 records that result only through `forensic-sequence-181-settlement.json`: an immutable local projection of the captured task-history command, exit status, traceback, source ordering, and the exact V6 binding/schedule/journal/claim/disclosure/acknowledgement hashes. It is explicitly not provider attestation. The missing 181 output and attempt paths merely corroborate the trace; absence alone is never the basis for the zero-contact settlement.

The V7 schedule contains sequences 181-330 (150 logical rows), with canonical SHA-256 `7866694887a6abcfb78fea4dd220e7ce3c5bb7ebbd85bc529ef18f06fddf89e8`. Its first journal row after admission is the trace-bound `forensic-precontact` record for 181, so dispatch begins at 182. Sequence 181 is not adopted as a V6 completion and has no output or provider-contact claim.

An explicit tracked engineering-reviewed HANNA cohort compatibility policy binds all 11 frozen task-contract hashes, the complete-short-story geometry, decision evidence, limitations, and the engineering-agent reviewer identity. Each HBQ direct-run override is derived only from that policy under `scope-compatibility-overrides/`. The V7 disclosure binds the policy and each override's exact bytes, schema, decision identity, and SHA-256 alongside the outbound prose, prompts, and response schemas. The successor runner validates the override before it reaches provider-attempt hooks. A remote launch still requires a byte-identical acknowledgement of the current disclosure, fresh local capacity evidence, a clean checkout at upstream, and `--allow-remote`.

```powershell
python evaluation-results/hbq-multisample-repeatability-v1-remainder-capacity-reset-successor-v7/executor.py `
  --work-root C:\Users\Haile\Documents\cwr-multisample-capacity-reset-v7-live-unique `
  --dry-run
```

This command is preparation evidence only and makes zero provider calls. Review the generated external-work-root disclosure before creating its exact acknowledgement artifact and using `--allow-remote`.
