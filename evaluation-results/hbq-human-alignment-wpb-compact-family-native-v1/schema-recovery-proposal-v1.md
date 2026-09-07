# WPB 0843 local schema-recovery proposal

Status: proposal only; no repaired measurement or new provider attempt is authorized.

The provider-free proposal verifier and adoption gate have passed independent review and four tests, including read-only verification of the retained local evidence. Published LF-normalized verifier SHA-256: `830ae3eae946064d53df4fd95c88f3db402322fa939ff306d61fc59080c3fbd8`. The exact adoption-candidate record is 1,148 bytes with SHA-256 `c06b66a5b48b1550f6bdb9a665d72d7944284e1c3275d00f43c1b15a59827488`. These checks establish the proposal's constraints; they do not supply owner adoption or authorize downstream continuation.

The approved WPB recovery admitted one replacement for `wpb-pair-wpb-en-0834`, preserving its original failed attempt and 89 earlier successes. The next cell, `wpb-pair-wpb-en-0843`, produced a terminal structured-output validation error. The campaign stopped at 90 accepted logical cells, one terminal cell and 38 untouched cells. No complete-campaign metrics or fit are available.

Read-only reconciliation found exactly one completed local-session agent message. Its JSON passes the frozen response schema except for two evidence strings: `A.evidence.core` has 182 Unicode code points and `B.evidence.craft` has 183, against a limit of 180. The proposed deterministic projection retains the first 180 code points of those two strings. Every other parsed value, including scores, coverage and winner, remains identical. The projected JSON passes the same schema and frozen WPB core response validation.

## Exact commitments

| Artifact | SHA-256 |
|---|---|
| Terminal broker outcome | `ca63efa971bf358cd35e544dd7fafc4283d42d20e309cdded00e3572cee465a3` |
| Original agent-message UTF-8 bytes, 1,390 bytes | `cc3523ce0ea0ff5b3f447e80a60a5ac5367ec8c2175549035dcc88e8976e9380` |
| Proposed projected message | `9e1b1b529d0f7023efb1e9663ad5092cfc0b7c431b0bf123375818f5db7709cd` |
| Frozen response schema | `3e7ff15aa844dd6f6b3c8c091cae5335eb1b290ca5eeddabb0eab6c29afc6b0e` |
| Local no-tool session attestation | `59aa037ef6363e897a9102932b639287eaec11a0b7cc27e31a100e3ebfef004a` |

## Proposed owner decision

Accept this exact local-session projection as one explicitly schema-recovered WPB measurement, with no new provider attempt for `0843`. Preserve the original message, terminal outcome, complete predecessor campaign, accepted `0834` replacement and proposed projection separately. Continue only the 38 untouched cells under current reviewed route and source gates, stopping on any unresolved result. This decision would not authorize retries of other terminal samples.

The adapter rejected the malformed output before retaining a completed native CLI envelope. The session attestation therefore lacks a request-ID-to-CLI-envelope binding. The projection must never be presented as an ordinary CLI-envelope-backed admission. If the full campaign eventually completes, report the evidence mix explicitly: 128 ordinarily admitted cells and one local-session schema-recovered cell. Retain the limitations of requested-only model/effort identity and unproven endpoint contact cardinality.

No numerical score is chosen, refitted or changed by this projection. Nonetheless, accepting weaker transport evidence after observing a failure changes the original admission contract. It requires a new explicit owner adoption bound to these exact hashes, followed by independent implementation and evidence review. Grok allowance/rearm authorization alone does not adopt this proposal. Until adoption, the campaign remains incomplete and both fitting and WPB Sol judging remain closed.

## Verification and completion gates

The verifier must enforce exactly the two specified string changes, preserve all other parsed values, reject changed source commitments, require an affirmative post-incident owner adoption, and retain the missing-envelope limitation. Continuation must bind the added lineage at every contact and admit exactly one vote per logical cell. Full analysis must require all 129 cells and preserve this amended evidence classification through the Grok selection freeze and subsequent unchanged-byte Sol comparison.

All source and diagnostic files remain local. This proposal contains commitments and protocol metadata only; it sends no text to a provider and grants no release, confirmation or promotion authority.
