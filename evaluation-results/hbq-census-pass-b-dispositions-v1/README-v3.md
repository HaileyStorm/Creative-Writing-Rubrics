# Saved census regeneration v3

`regenerate_v3.py` regenerates count and declaration-disposition exports from a
complete saved v2 run, registry v6, TTCW snapshot 051 and its qualification delta
052. It has no historical-reader, collector, scorer or provider execution path.
Earlier versions and their evidence remain immutable.

Supply a private recipe with `policy: historical_cohort_count_regeneration_v3`
and a `sources` object. Its roles are the names in `PINS`, plus
`registry_terminal`. Each pin contains `root` (`repository` or `control`), a
root-relative `locator`, `sha256` and `bytes`. Bind the registry terminal to its
exact saved receipt. Keep the recipe and generated research exports local.

```powershell
.venv\Scripts\python.exe -B evaluation-results\hbq-census-pass-b-dispositions-v1\regenerate_v3.py --control-root <control-root> --recipe <private-recipe> --recipe-sha256 <exact-sha256> --output-root <fresh-owned-output>
```

Add `--dry-run` to verify all finite inputs without creating output. It never
falls back to executing an incomplete cohort. All nine saved report/private
pairs must match their checkpoint, terminal, descriptor and saved report.
Private ledgers are hashed and copied as opaque bytes. A completed output has a
`report.json`, `terminal.json`, saved implementation/recipe and the unchanged
nine cohort exports. Interrupted output is retained; choose a fresh output after
reconciling it rather than overwriting it. Repeating the same inputs in another
fresh directory yields the same report and terminal bytes.

Registry declarations have explicit unresolved, metadata membership, inherited
reference, mapped-scope or other qualified-scope dispositions. These namespaces
overlap and cannot be summed into independent votes. TTCW 051 stays unchanged;
052 qualifies its single pending accepted Grok ordinal 114. The resulting
historical admissions are 303 Grok and 658 Sol against the original 3,108 planned
requests. The Sol comparison in 052 is reuse. Saved scalar/order summaries are
not updated by this export.

This is partial census progress. It does not establish current tools-disabled
collection, native capacity, physical contact totals, human validity or release
acceptance. Unresolved declarations and the full research Goal remain open.
