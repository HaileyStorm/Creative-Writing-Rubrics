# HBQ-RS first-remedy portfolio v1

This is the public coverage manifest for the 77 owner-reviewed first-remedy
findings from the full-leaf audit. It is a planning boundary, not a rubric
change, a provider run, or a release decision. Its initial singleton-only
budget is fixed at 1,140 calls: R0 0, L1 72, L2 216, P1 132, S1 420, and S2
300. Any clarification or other successor must be separately frozen and may
cover only the affected finding(s).

The public map commits every selected finding ID and the exact package
partition: R0 2, L1 1, L2 3, P1 11, S1 35, S2 25. Those 77 findings resolve
to 81 leaf memberships and 80 unique public leaves; only
`penalty.purple_prose.fatigue` appears twice. The manifest pins the full audit,
findings, triage, triage summary, six committed source-part hashes, and the
CWR parent revision.

There is a deliberate public-provenance gap. Package membership was reconciled
from six owner-reviewed source parts and a private classification, whereas the
published semantic triage intentionally collapses 77 first-remedy experiments
and 59 watches into 136 `needs_empirical_test` rows. This package therefore
publishes the IDs and counts needed to verify coverage, but no local source
paths, source-part prose, private artifacts, or model transcript.

R0 consumes no new calls. Its two fatigue findings are already bounded by the
settled public figurative result: fatigue was 12/12 in baseline and 12/12 in
the scope-rendering arm, for 24 relevant singleton calls. That is a
development-level `NO_CHANGE`/watch signal only. The result is `NO_GO` and
does not promote an overall treatment, wording, ownership change, split, or
weight change.

Run `python verify_portfolio.py --check`. The verifier has no provider or
execution mode; it fails closed on a changed source hash, package partition,
triage status, CWR parent ancestry, leaf coverage, repeated-fatigue rule, or
R0 aggregate.
