# Census F: retained Dryad Grok collection

This provider-free census replaces Census A's Dryad Grok projection. The pinned final-analysis file supplies only `freeze.admission.record.collection_record`; the census does not inspect human targets, scores, prose or rationale fields to select rows or interpret verdicts. Historical controller files are hashed as source artifacts and never imported or executed.

The deterministic join covers 100 collected story-pass pairs, 2,300 scheduled positions, 17,800 ordered four-state leaves, 2,297 ordinary native identities, 33 historical exclusions and 2,210 owner entries. It preserves the three recovered positions 70, 254 and 370 and the 18 retained parallel-prefix descriptors. Replacements, excluded attempts and adopted projections add no independent works or extra votes. The downstream analysis subset of 82 passes is distinct from the collected 100.

The join verifies selected source/prompt/schema bytes against the frozen plan, exact pass/request/criterion order against the selected schedule, pass and native identity commitments, and exact owner/terminal memberships. For 2,208 positions it checks retained terminal raw output states against the normalized collection states. Ordinal 279 has a pinned native runtime-data recovery: its original terminal remains ambiguous and the separate adopted recovery supplies states without a new contact. Ordinals 254 and 370 use their exact adopted projection and protected evidence pins; no repair or normalization is performed here.

Ninety prefix/replacement positions, including ordinal 70, currently retain collection metadata commitments rather than a direct native artifact join. Their private ledger records their exact ordinals, source/prompt/schema commitments, state projection and historical replay-input commitment. The finite prerequisites for follow-up are the first three passes' checkpoint-head/run-manifest commitments, the fourth pass's prefix checkpoint/run-manifest and recovered manifest commitments, and the original/replacement native artifact locators attested by those records. Missing direct joins do not mean missing contacts. Native envelope storage bytes are separately committed but not reconstructed by this census. Full physical-contact disposition closure, provider/model/runtime attestation, modern strict import and full-score replay remain unverified.

The declared historical collection hash `2c5618dcfc2b03c9044bdc6dd8d4c7d73aeb8205f31aa7ffdb3be1df25bcf636` differs from the canonical hash of the pinned embedded collection projection, `efa9bbbb303087161a83fbbbc550e8633a724dfc52fac2de36a4ca673c236b4c`. Both are retained explicitly without asserted equivalence. The native identity commitment matches `2e0451978791ad524b952a22e2b48f7d67348f16f8c22320783d94e9a2bab7ee`.

One bounded implementation inspection accidentally displayed terminal quote/rationale objects in tool output. No selection, state normalization or missingness inference used that display. The implementation emits only counts/hashes/source locators publicly; native identities, state rows, owner metadata and artifact lists remain in the private ledger.

Run from the repository with a retained Documents root or a provider-free exact relative-path mirror:

```powershell
python -B evaluation-results/hbq-census-native-f-v1/census.py --source-root C:\Users\Haile\Documents --output-root C:\Users\Haile\Documents\cwr-resume-control-20260919-r1\successor-program-20261004\census-f\run-001 --dry-run
```

Remove `--dry-run` only for the owning root's fresh private run. The output must not exist and must lie outside the repository and retained input roots. Dry-run creates no output. A real run exclusively writes the recipe, implementation/common source, invocation, public `census.json`, private `private-slots.json` and immutable terminal receipt. Missing or changed source pins fail explicitly and retain any real-run partial receipt; there are no contacts or retries. The recipe uses finite pinned files and paths derived from their metadata, with no discovery scans.

Focused verification: `python -B -m pytest -q tests/test_native_census_f.py`.
