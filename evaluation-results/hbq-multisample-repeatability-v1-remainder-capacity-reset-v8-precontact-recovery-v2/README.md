# V8 seq265 precontact recovery v2

This is a default-off, exact-one successor for the V8 sequence-265 capacity failure. It is not live-execution evidence and does not authorize provider contact.

`prepare_recovery` is provider-free. It captures the immutable, complete-line rollout prefix ending at reviewed terminal line 75128, writes that raw snapshot only in a fresh external recovery root, and binds the independently reviewed full-prefix byte count and SHA-256, old guard, failed capacity evidence, frozen delegate bytes, accepted V8 prefix, and exact next event. Do not commit a recovery root or its captured private transcript.

`preflight_recovery` permits later source suffixes but rejects a changed, reparsed, or truncated captured prefix; it also revalidates the old guard, failed evidence, runtime identities, no-orphan state, exact acknowledgement, and V8's independent current 600-second capacity gate.

`settle_one_after_review` remains disabled unless `allow_remote=True`. It writes one immutable intent before calling frozen V8 `_settle_one` once. A later retry, crash, ambiguous result, changed target, retry pause, output/session artifact, journal evidence, or completed claim is terminal: do not resend. The terminal transcript proves a capacity failure at `_settle_one` entry before V8 attempt intent/provider dispatch; it does not prove a global absence of processes or provider contact.

Native read-only prefix check is opt-in only:

```powershell
$env:CWR_V2_NATIVE_ROLLOUT = 'C:\absolute\rollout.jsonl'
python -m pytest -q tests\test_hbq_multisample_repeatability_v1_remainder_capacity_reset_v8_precontact_recovery_v2.py
```

Normal live invocation belongs to the parent-controlled review/push lane. Fresh capacity should be observed immediately before that invocation; preparation intentionally does not consume or manufacture a capacity observation.
