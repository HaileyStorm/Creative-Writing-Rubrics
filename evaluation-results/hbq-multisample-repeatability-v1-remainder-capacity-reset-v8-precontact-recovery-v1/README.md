# V8 seq265 precontact recovery v1

This is a provider-free recovery controller for the immutable seq265 guard
intent that failed during capacity-evidence validation. It binds the old guard,
the exact event, the pinned adapter/guard/runtime identities, accepted V8
prefix, a read-only Codex app rollout JSONL, and two distinct capacity files:
the immutable failed-capacity artifact named in the historical invocation and
fresh current-capacity evidence for the separate <=600-second dispatch gate.

`prepare_recovery` and `preflight_recovery` never call a provider. The parser
requires the root task session, exact adapter invocation, unified session 27739,
and the terminal pre-settlement capacity error. It never treats the historical
failed-capacity file as fresh authorization. Live settlement is explicitly
NO-GO until the real app-generated rollout is independently reviewed; the
former guard root is never modified.
