# HBQ multisample repeatability V8 continuation

V8 is a fresh, fail-closed descendant that leaves the live V7 root immutable. It adopts exactly one completed V7 output: sequence 182 (`hanna-523` / `naplan_narrative_2022` / repetition 1). The adoption is bound to V7's binding, schedule, intent-only journal, dead claim, disclosure, acknowledgement, capacity proof, runtime, canonical six-file output manifest, one recorded contact, and provider session `01a04569-0c0c-7501-ab85-0f9e2f128231`.

`v7-sequence-182-settlement.json` records the local post-dispatch validator failure that prevented V7 from journaling the completed output. It is local immutable evidence, not provider attestation. Sequence 181 remains a trace-proven zero-contact logical prefix and is deliberately excluded from session validation; all output-backed cells, including adopted 182, require unique provider-session evidence.

The V8 schedule is the canonical 149-row suffix 182–330, SHA-256 `98fc94c7cd75bbea4f913a144871f31a0ea743695611f797fb86ca7e2e977bd7`. Its immutable admission journal marks 182 as adopted, so any new dispatch starts at 183 (148 rows). The minimum physical-contact count for the full V8 schedule is 269; V8 reports the adopted V7 contact separately from its own journaled contacts.

V8 reuses the exact V7 engineering-reviewed HANNA cohort compatibility policy (rather than copying or relabeling it). Per-artifact HBQ overrides derive from that policy and are bound into the disclosure and checked again at the provider boundary. A remote launch still needs a byte-identical disclosure acknowledgement, current local capacity evidence, a clean pushed runtime, and `--allow-remote`.

```powershell
python evaluation-results/hbq-multisample-repeatability-v1-remainder-capacity-reset-successor-v8/executor.py `
  --work-root C:\Users\Haile\Documents\cwr-multisample-capacity-reset-v8-live-unique `
  --dry-run
```

This preparation-only command makes zero provider calls. Review the generated external work-root disclosure before any separately acknowledged remote invocation.
