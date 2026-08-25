# QPC24 two-pass product confirmation v1

This provider-free package freezes a new QPC24 product-confirmation successor
at CWR commit `4ce1204`. The external private controller selects six
whole-work passes untouched by the historical v4/v5 execution roots.

The target is 60 voting provider calls and 1,326 positions: six complete
221-leaf `prose.novel` evaluations, each partitioned into nine 24-question
calls and a required five-question remainder. Historical contacts are immutable
nonvoting provenance, not inputs to this result.

This is not a sparse or reduced-fidelity evaluation. Every selected pass keeps
the normal full-rubric 221-leaf, 9×24+5 path. Two passes reduce only the amount
of repeatability evidence: agreement is stability evidence and disagreement is
instability evidence, without a majority vote. The historical 150-call,
five-repeat plan remains the extended validation path and is not replaced. This
successor does not alter the CWR runtime or any default evaluation setting.

There are three predeclared whole-pass reserves. A reserve can replace one
affected primary pass only for a recorded local transport ambiguity. It cannot
compensate for a substantive miss, unfavorable outcome, schema/model failure,
or extra sampling request. Selection, reserves, contact ledger, source paths,
and rendered prompt hashes stay in the external private root; this public
package has neither private prose nor an execution surface.

Future dispatch is explicitly constrained to zero-paid Codex `gpt-5.6-sol`
with `high` reasoning, no paid/API fallback, and independent review before
any contact. This package itself makes zero calls.

From the CWR root:

```powershell
.venv\Scripts\python.exe evaluation-results/hbq-qpc24-two-pass-product-confirmation-v1/study.py verify
pytest -q tests/test_hbq_qpc24_two_pass_product_confirmation_v1.py
```
