# Local historical WPB dependency fixture

[manifest.json](manifest.json) records the exact five shared-tool sources required by the frozen WPB dispatch tests. The source bundle comes from private provenance and remains outside this public repository. Only this documentation, the manifest, and the test loader are published.

To run the historical integration tests with an owner-provided local bundle:

```powershell
$env:CWR_WPB_HISTORICAL_FIXTURE_ROOT = 'C:\path\to\local\fixture'
.\.venv\Scripts\python.exe -m pytest tests/test_hbq_human_alignment_wpb_grok_batches_v1.py
```

The local directory must contain the matching manifest and all five files at their declared relative paths. The loader verifies both manifests and every source hash before creating an isolated package. It restores module state afterward. Provider and CLI boundaries are mocked; the installed shared runtime is not replaced.

With the variable unset, these tests explicitly skip. A configured missing, invalid, or mismatched bundle fails. The original local WPB source-freeze prerequisites still apply; setting this variable does not establish clean-host or Linux validation. Do not copy the private source bundle into this repository.
