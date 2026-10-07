# Historical fresh96: frozen schedule and output directory membership

This provider-free census binds the historical fresh96 Sol output namespace to
its exact frozen schedule: 64 unique cells, two candidates, 32 items and sixteen
prompt groups. Every scheduled cell's directory name exists exactly once; no
extra directory is accepted. Both candidates cover the same item membership.
The missing collector remains unresolved. Directory membership adds zero
accepted measurements, provider votes or observed leaves and does not establish
request acceptance, output validity, retry cardinality or confirmation eligibility.

`recipe.json` pins the exact Documents-relative freeze and output-root names,
the manifest and raw schedule bytes, candidate and analysis-rule declarations,
and the study/executor source implementations. The executor derives directory
names from sorted compact JSON `{source: cell_id}`, UTF-8, no ASCII escaping,
no NaN, trailing LF, then the first sixteen SHA256 hex characters prefixed
`v10-sol-`. The implementation checks unique cell/candidate/item membership,
stable item-to-prompt-group assignments, transform collisions and exact names.

The four-field manifest binds the declared logical schedule hash. Selective
projection retains only study/hash declarations and cell/candidate/item/group
identifiers. It does not regenerate the full schedule's logical hash. The raw
schedule hash and byte count are independently checked. Both pinned files and
the immediate plain-directory set are rechecked before creating completed output.
Reparse/symlink inputs are rejected. Only top-level directory names are inspected;
directory contents, native receipts, sessions and outcome reports are not opened.

The reused pinned lexical reader decodes the whole schedule as UTF-8 for scanning.
It parses/materializes only selected JSON metadata values; unselected request
payload and human-target values are skipped. This is not a byte or UTF-8 nonaccess
claim. A focused synthetic guard demonstrates that invalid unselected JSON
escapes are not materialized while exact directory mismatches reject. An earlier
invalid-UTF8 test failed before real dataset access; its original bytes are
retained privately and the boundary description was corrected explicitly.

Actual execution completed at 2026-10-07T04:31:40Z, exit zero. Root readback
verified saved geometry, membership and ledger commitments, exact source
snapshots, namespace and limited claims without rereading the real schedule,
opening native output contents or rerunning the census. Public aggregate SHA256:
`511ec660c73b7e85c6c38f251017a091bce28c868c0e8760b02880a810138f30`.
Private ledger SHA256:
`7c8469b89724d86d4a735f9fc9f429c0a5ccc86c9a39d117afa6254adc0bae35`.
Raw logical identifiers remain in the private ledger; aggregate and code are public.

The frozen registry V6 remains unchanged. This evidence has the existing
`nonvoting_output` relationship; it does not replace the `unresolved_locator`
collector edge or increase qualified measurement counts. A future registry
extension can reference the saved commitments without replaying native outputs.
No provider calls, new votes, targets, scoring, promotion or release occurred.

Replay from the repository root, using the exact relative root names in the recipe:

```text
python -B evaluation-results/hbq-census-fresh96-directory-metadata-v1/census.py --freeze-root <Documents>/<recipe-freeze-root> --outputs-root <Documents>/<recipe-outputs-root> --output <fresh-private-output>
python -B evaluation-results/hbq-census-fresh96-directory-metadata-v1/test_census.py
```

Output must be fresh and outside the repository and retained input roots. It
contains report, private ledger, recipe and implementation, with a completion
receipt written last. Retained historical failures and ambiguity remain intact.
The full research matrix, live collections and prospective gates remain incomplete.
