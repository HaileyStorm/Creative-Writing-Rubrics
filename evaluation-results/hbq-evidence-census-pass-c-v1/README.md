# Evidence census C: retained LAMP Batch-3/5

This provider-free projection reads only the descriptor's retained plans, source artifacts, collection roots, receipts and code bytes. Historical collectors and admission readers are never imported or executed. It adds the main Batch-3/5 native leaf joins and the separately identified planned-repeat joins to the partial census begun in passes A and B. Earlier LAMP collections remain unresolved.

The main denominator is 522 planned requests per endpoint and 8,107 observed accepted leaves. Planned repeats have 72 requests per endpoint and 1,120 observed leaves, which are not extra human-alignment votes. Preserve all 29 source groups, including the separately retained 25 admitted and four excluded groups. Only two excluded groups have unadmitted requests; two retain complete request leaves but fail the historical score/admission criteria, which this census does not recompute. The 1,188 client sessions include 1,178 accepted native identities, two unadmitted Sol native identities, and eight Grok slots classified definitely not contacted.

Sol main 57 keeps its original controller failure and its independently pinned local schema repair. Main 68 and repeat 21 stay unknown-exit, unadmitted and no-resend. Planned-repeat IDs and original ordinals remain distinct even when prompt or source bytes are identical. Accepted leaves preserve request and question order. The adapter fails on missing or mismatched pins, overlapping ordinal lineages, wrong native identities, altered leaf order, or changed intent, contact, terminal or repeat-parent bindings.

Run from the repository with its Python environment:

```powershell
.\.venv\Scripts\python.exe -B evaluation-results/hbq-evidence-census-pass-c-v1/census.py --control-root <private-control-root> --output-root <fresh-private-descendant> --dry-run
.\.venv\Scripts\python.exe -B -m unittest discover -s tests -p test_evidence_census_pass_c.py
```

The dry run validates the complete projection and prints canonical JSON-object digests without writing output. Omitting `--dry-run` creates a fresh output directory outside the repository and retained LAMP tree; existing output is never overwritten. `census.json` contains aggregates, hashes and allowlisted source locators. `private-slots.json` remains task-local and contains hashed slot/source/native identities, ordered leaf identities and verdicts, original repeat ordinals and planned-repeat IDs, and immutable lineage commitments. Neither export includes prose, rater IDs, raw native UUIDs or absolute input paths. No public observed summary is generated here.

This remains a partial census. Retained contact admissions are local controller evidence, not a physical-contact count. Grok broker receipts commit native envelope hashes without materializing those envelopes here. Historical Sol requested settings do not establish native model/effort attestation. Plan and collection runner hashes are retained separately rather than treated as an identical full execution contract. Source bytes are read only for their hashes; unused preferences, rankings and rationales are not projected.
