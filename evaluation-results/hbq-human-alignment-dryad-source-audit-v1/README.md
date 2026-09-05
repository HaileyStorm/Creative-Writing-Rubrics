# Dryad human-rating source audit

The supplied [Doshi and Hauser dataset](https://doi.org/10.5061/dryad.qfttdz0pm) adds an independent corpus of 293 short stories with 3,519 blinded human evaluations from 600 evaluators. This is source-readiness evidence, not a model-alignment result.

The source counts reconcile from 500 writer records to 296 completed writers, then 293 after the source protocol's three human-only AI-use exclusions. The 600 completed evaluators supplied 3,600 story slots; 81 slots concern excluded writers, leaving 3,519 evaluations. Each retained story has 9–14 evaluations.

The minimized local derivative retains all twelve complete 1–9 blinded scales: novel, original, rare, appropriate, feasible, publishable, well-written, enjoyed, boring, funny, twist, and future. The source processing note says the question underlying `tt_badly_written` changed to well-written while its database name stayed unchanged; the derivative applies no reversal. Twist is not relabeled as surprise. These dimensions do not establish a full HBQ-RS mapping.

Stories, individual ratings, participant identifiers, demographics, self-ratings, and post-disclosure judgments are not published here. The local derivative retains opaque evaluator indices for clustered uncertainty estimates and story IDs/text for leakage checks. Writer condition and topic remain local analysis strata, not judging inputs. Endpoint measurement, target aggregation, splits, and any rubric correspondence must be frozen before judging or optimization; confirmation remains unopened. Do not pool this corpus with HANNA or WPB scales.

The original supplied ZIP and the six-axis first derivative are preserved for provenance. The expanded twelve-axis derivative adds previously omitted blinded outcomes. The extraction reads bounded archive data without executing the supplied Stata/Python scripts or making provider calls. [result.json](result.json) records content commitments and counts. Boring retains its negative orientation; no composite across the twelve scales is established. Exact survey wording is unavailable in this source audit except for the limited well-written correction noted above.

[source.py](source.py) preserves the exact audited extraction program. Its `derive(archive_path)` function reconstructs both CSV byte streams and the complete reconciliation object from the pinned supplied ZIP. Its read-only `--check-only` command compares those outputs with an existing local audit root; `--self-test` additionally rejects a README-only archive substitution before decompression. It requires only the Python standard library. Historical write/repair modes are retained as audit provenance, not as a runtime ingestion interface.

```text
python source.py --archive PATH_TO_SUPPLIED_ZIP --root LOCAL_AUDIT_ROOT --check-only
python source.py --archive PATH_TO_SUPPLIED_ZIP --root LOCAL_AUDIT_ROOT --self-test
```

The archive contains no license file. Reuse relies on Dryad's dataset-wide CC0 terms, sections 1(a) and 4(a–b), checked September 5, 2026; the DOI landing page itself has no explicit license badge. [Dryad terms](https://datadryad.org/terms).
