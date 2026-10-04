# Census A retained metadata projection

This provider-free adapter implements a **partial census A**, following the local index section of `docs/ALIGNMENT_EXECUTION_PLAN_20261004.md`. It reads only the source-descriptor allowlist under the supplied control root. It never executes retained collectors/readers, follows embedded source paths, scans account homes or generic logs, or contacts providers. The allowlist excludes unused confirmation preferences and rationales. Some existing admitted evidence files contain historical labels or prose alongside metadata; the adapter hashes their bytes and selects metadata fields without exporting those contents or using their values.

Run from the repository, with an existing private evidence root and a new output directory:

```powershell
.venv\Scripts\python.exe evaluation-results/hbq-evidence-census-pass-a-v1/census.py --control-root <retained-control-root> --output-root <fresh-private-output-root>
```

The command writes `census.json` and `private-slots.json` exclusively to a fresh directory and refuses an existing destination. Both exports are private metadata descendants; neither is a public aggregate. Input files remain unchanged. Source byte hashes bind each projection to its retained parent; the descriptor hash binds the allowlist. A failed write may leave a partial descendant; preserve it and choose another fresh directory rather than overwriting it.

`declared` fields quote retained count metadata. `observed` fields count the selected lists, packet records and normalized native verdict rows. Accepted request counts do not establish physical contacts. Dryad Sol's 17,800 verdicts are retained declarations without native verdict rows in this allowlist; consolidated Dryad Grok includes observed rows and retained/excluded native identity lists. Earlier Grok prefixes are ancestors, not extra votes. The old 51,968/53,990 floors require explicit source reconciliation rather than subtraction across different denominators.

TTCW and Pron join packet ordinals to their retained plan and report whether the plan byte pin matches. Slot identity includes cohort, endpoint and logical sample identity; identical content does not merge planned independent samples. Replayed duplicate records in one slot do not add votes; conflicting accepted commitments are unresolved. Declared Pron nonresponse remains missing native evidence, including eight missing leaves; derived CANNOT_ASSESS scoring fill never becomes a native vote. An unresolved or declared-nonresponse identity remains reserved with `no_resend`. Identity exports contain hashes rather than native thread IDs, work/author names, scores, labels or raw model responses.

LAMP source groups, variants, pass rows, repeat indices and retained endpoint receipt counts remain separate. Planned pass rows do not prove accepted native votes. Ambiguous/nonaccepted receipt ordinals remain reserved. The repeat readout's declared accepted counts are not extra human-alignment votes, and R396 rescoring adds zero native votes. Matching TTCW/Pron leaf payload hashes establish leaf equality only; full contract and exact-current compatibility remain unresolved.

`remaining_joins` in the descriptor and each source's `unresolved` list define the unfinished work. Full native attempt/recovery dispositions, source rights/form/overlap, rater and pair ancestry, LAMP packet/leaf/repeat joins and Dryad Sol rows are needed before full census A closure. Pass B still covers full-book/QPC24, multisample, poetry, revision ledgers and all other declared empirical roots. An absent allowlisted source gets an explicit absent disposition, never an inferred zero.

Narrow local verification:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_evidence_census.py
```
