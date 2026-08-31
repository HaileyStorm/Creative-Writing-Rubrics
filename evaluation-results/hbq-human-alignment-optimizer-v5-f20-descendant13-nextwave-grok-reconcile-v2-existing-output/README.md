# Descendant-13 existing-output recovery v2

This is a provider-free, one-way collector for the ten immutable Grok envelopes in the descendant-13 next-wave root. It verifies the committed generator/catalog, the exact SHA-256 bytes of every source envelope, every prepared artifact, the matching prompt and launch intent, the original terminal result, the reported `grok-4.6-build` one-call model-usage shape, and unique envelope request/session IDs before writing one new disjoint recovery manifest.

All ten proposals are rejected as invalid profiles: seven have `profile geometry drifted` and three have `profile factors drifted`. The manifest retains each proposal's instruction and change summary only as a development idea. It creates no candidate, selection, promotion, runtime, confirmation, or native-contact claim.

Example:

```powershell
python recover.py --source-root C:\Users\Haile\Documents\cwr-hanna-desc13-grok-wave-f7ac506-20260831a --target-root C:\Users\Haile\Documents\cwr-hanna-desc13-grok-wave-recovery-v2-20260831a
```

The source root is never modified. The target must not exist and must be outside both this repository and the source tree. `process_launches: 0` refers only to new provider/executor launches; local Git subprocesses used to verify pinned provenance are not provider or executor launches.
