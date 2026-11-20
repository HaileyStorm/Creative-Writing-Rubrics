# Benchmarking with HBQ-RS

Use the stack as a *structured* judge, not as a single scalar disguised as truth.

## Read a score report

- **Canonical score:** the deterministic result for the artifact at the scope actually judged. A manuscript score is not reconstructed from chapter or scene scores; those remain diagnostic children unless a separately saved composite profile is explicitly reported.
- **Controls:** `hard_gate_status` reports objective eligibility separately from quality. `VALID` means every applicable binding requirement passed; author preferences and weighted goals can affect score but not this status.
- **Coverage:** the weighted share of applicable point-bearing criteria resolved `YES` or `NO`. `NOT_APPLICABLE` leaves are excluded; `CANNOT_ASSESS` leaves reduce coverage rather than counting as failures.
- **Observed score:** the deterministic score from assessed applicable criteria after capped penalties. Report it with coverage and controls, never alone.
- **Bounds:** `lower` and `upper` describe the scorer's sensitivity to unresolved `CANNOT_ASSESS` criteria. They are not confidence intervals or error bars. In the historical scorer, a lower unassessed ladder threshold can suppress a higher `YES` before bounds are computed; resolving the lower threshold may restore that `YES` and produce a score above the reported upper bound. Do not treat these historical bounds as a guaranteed envelope of all resolved scores.

## Report the control fields

Every published score should include:

- `bundle_id` and bundle version
- `hard_gate_status` (`VALID` / `INVALID` / `UNRESOLVED`)
- `coverage` and `minimum_coverage`
- `status` (`SCORED` / `PROVISIONAL` / `INELIGIBLE` / `UNRESOLVED`)
- `final_score.lower` / `observed` / `upper`
- judge identity, prompt hashes, and whether order-swapped pairwise was used

A leaderboard that drops hard-gate failures into the quality average is lying about both eligibility and craft.

## Recommended protocol

1. Freeze the bundle and any dynamic task module before candidates are visible.
2. Grade independently. Do not condition later leaves on a desired ranking.
3. For close finalists, run `prompts/judge/PAIRWISE_FINALIST_PROMPT.md` twice with swapped order. Disagreement is a tie or an escalation, not a coin flip.
4. Attach judge meta-rubrics when you are measuring the *judge*:
   - `meta.judge_bias_and_calibration_control`
   - `op.select.judge_confidence_and_evidence_quality`
   - `op.select.rubric_application_quality`
5. For long work, follow `prompts/judge/LONG_FORM_PROTOCOL.md`. Never publish the mean of chapter scores as a manuscript score.

## Name the judge condition precisely

A model name is not a reproducible judge. Record the exact checkpoint or revision, quantization, serving runtime, prompt and schema versions, sampler settings, role, batch size, and polarity. Two roles using the same checkpoint are useful repeated conditions, but they are not an independent-model ensemble. Treat a later fine-tune or specialized checkpoint as a new condition.

Sampler settings belong to the task. A sampler that helps drafting may hurt grading or exact evidence transfer, so do not carry a creative-generation profile into judging without a separate calibration result. Model confidence is also diagnostic until it is calibrated against repeated decisions and external labels; it does not change canonical score or coverage by default.

The experimental `hbqrs.repeatability.paired_response_envelope` rejects duplicate
JSON object keys by default, including differently escaped spellings of the
same key. Historical raw responses can be reconstructed with the explicit
`response_parse_policy="legacy_last_key_v1"` option, which retains the former
last-key behavior. Existing receipts and their hashes do not change. The v1
receipt binds the raw response hash and parsed output but does not record the
parse policy; retain the raw response and the caller's policy separately when
that distinction matters. This parser check does not prove native receipt
authenticity, model identity, or that a paired request actually swapped inputs.

## Confidence diagnostics

`report.confidence` remains for compatibility. It is the legacy domain-point-weighted mean across assessed domains, not an effective-leaf calculation.

Versioned score reports carry the optional `confidence_diagnostics` field. Unversioned `score.json` files remain v1 evidence; current runner surfaces leave those parents untouched and atomically write a hash-bound `score.v2.json` descendant. V2 reports secondary role diagnostics for `domain`, `hard_gate`, `penalty`, and `supplemental` leaves using effective leaf weights. They never change the canonical score, coverage, penalties, gates, bounds, or status. An empty or wholly unassessed role has `null` ratios and is rendered as **Not observed**.

The `cwr score` command emits v2 by default. Use `--report-version 1` only to independently reconstruct the semantics of an immutable runner-owned `score.json` parent; the explicit v1 path restores the same materialized weight-profile audit and does not claim byte-identical serialization or reinterpret v2 evidence as v1.

## Intervals and coverage

`CANNOT_ASSESS` contributes uncertainty to the reported interval. Historical ladder normalization can make that interval too narrow when an unassessed lower threshold suppresses a higher `YES`, as described above. The optional `uncertainty_preserving_ladder_v1` policy is a separate candidate, not the default or a proven universal bound. If coverage is below the bundle threshold, the result is `PROVISIONAL` and must not drive unattended acceptance. Missing modalities (no audio for an audio leaf) are `CANNOT_ASSESS`, not `NO`.

For example, `synthetic_A` in the [scorer influence aggregate](../evaluation-results/hbq-scorer-verdict-influence-v1/aggregate.json) has a historical upper bound of 39.6799 when `core.holistic_artistic_success.threshold_1_functional` is unassessed. Resolving that one threshold as `YES` yields 41.6799. This is a mechanical counterexample, not an estimate of how often the issue occurs in practice.

### Inspect finite scorer completions

For a strictly admitted verdict bank with a manageable number of unassessed or
omitted questions, the optional completion-envelope module can rescore every
combination of `NO`, `YES` and `NOT_APPLICABLE` for score- or eligibility-
affecting questions while holding the other verdicts and task contract fixed:

```text
python -m hbqrs.scoring_completion_envelope prose.short_story verdicts.json --artifact-id STORY_ID
```

For new structured files, add `--input-policy unique_keys_finite_v1` to reject
duplicate keys and non-finite or non-JSON-compatible values in the verdict file
and any supplied task contract. The output records this policy and the exact
file-byte hashes. The default `historical_v1` parser preserves earlier command
behavior; strict import admission alone does not detect keys discarded by that
parser. This option does not authenticate sources or validate evidence against
the artifact, and it does not apply to already-parsed Python API inputs.

The output keeps the historical score separately and reports the extrema of
the historical scorer's rounded results for the enumerated states. It does
not change the original verdicts or default score. Inputs must pass strict
import admission; conflicting compact-map question IDs are rejected in both
strict modes. Admission checks structure and declared evidence but does not
verify references or quotations against the source text. A missing question
is treated as unassessed, and the
calculation uses a synthetic scorer-only record for each of its possible
states; that record does not supply source evidence or an admitted judgment.
Unassessed supplemental questions are counted separately because the pinned
historical scorer excludes them from score and eligibility. Their individual
reports and issue lists may still differ. The calculation refuses an
unrecognized scorer implementation rather than assuming this property holds.

The number of combinations grows threefold per unknown. The default maximum
is 19,683 combinations; `--max-cases` can set a lower limit. The module declines
to return a numeric envelope when the requested case limit would be exceeded
or when any completion is not `SCORED`. In particular, an uncertain hard gate
may make some completions ineligible. A returned envelope is limited to the
specified scorer substitutions and fixed inputs; it is not a statistical
confidence interval, a calibration result, a human-alignment finding, a
guarantee about model uncertainty, or an unattended acceptance decision.
Consider applicability and the evidence for each criterion separately.

### Inspect guarded grouped completions

For a fully supplied verdict bank, the optional Python API
`hbqrs.scoring_grouped_completion.grouped_completion_envelope` can evaluate
independent scorer groups without enumerating every cross-group combination.
It requires strict v2 admission, a fixed assessed question in each domain,
valid fixed gates, distinct question IDs, and no subjective ladder crossing
domains. Unsupported inputs raise `ValueError`; use the finite enumerator when
its requirements and limits permit.

The default retains strict v2 admission for historical compatibility. For new
imports, pass `admission_policy="strict_import_v3"` to validate a supplied task
contract against the shipped schema before compilation. The result then includes
the admission policy and, when a contract is supplied, its schema digest. This
structural check does not establish that declared evidence is grounded in the
artifact.

The grouped method limits both assignments and assignment-count multiplied by
the number of selected questions. These are work estimates, not time guarantees.
Its extrema are fixed-input, scorer-only substitutions; they do not supply
evidence, new judgments, confidence intervals or human-validation claims.

### Inspect decision readiness

For two completed binary runs with frozen inputs, the optional Python API
`hbqrs.verified_pair_comparison.compare_verified_binary_runs` first uses the
offline run verifier on each run. It checks the shared task, context, scoring
configuration and scope-decision contents before reporting point order; changed
applicability, reused sessions and incompatible runs are kept separate. It also
reports the historical interval comparison, which has a different meaning from
point order. Its `interval_bounds_kind` identifies those historical bounds and
`interval_completion_envelope_guaranteed` is false: even strictly separated
historical intervals do not establish an order over every resolved verdict bank.
For separately bound direct-run task contracts, the optional
`hbqrs.verified_pair_completion.compare_verified_completion_runs` first checks
the verified pair's shared conditions, then strictly admits and evaluates each
original verdict bank against its own contract. It returns both finite completion
receipts and compares their bounds only when both are available; touching bounds
are inconclusive. The default cap is 243 assignments per bank, adjustable up to
19,683. Unsupported inputs raise; work-limit and non-scored completion cases
withhold the result. Completions vary each bank independently with all other
verdicts fixed, and do not establish shared evidence, human preference or provider
identity. This requires stable trusted local files, is not an atomic snapshot,
and supports the same direct-run scope as the verified-pair API.
This version supports task contracts with direct-run scope overrides and requires
stable, trusted local files. Saved provider and reviewer claims are not
independently authenticated, and local verification does not establish human
preference or literary correctness.

For a saved whole-work `full_judging` binary run, the separate opt-in
`hbqrs.verified_longform_context.verify_longform_contexts` verifies the binary
run and reconstructs the map's source/unit identity and deterministic task and
completion contexts. Its local receipt includes the scope proof and binary
verification details, including local paths. The check requires stable, trusted
files and is not an atomic snapshot. It does not establish that map summaries
are true, authenticate a provider or review, verify the preceding map-generation
passes, or compare two works. Other long-form scopes remain unsupported.

Run the optional readiness tool on an existing local v1 or v2 score report:

```bash
python -m hbqrs.decision_readiness score.json --threshold 50
python -m hbqrs.decision_readiness left.json --compare right.json
```

The tool reads saved reports without judging or rescoring. It preserves their
status, separates positive coverage from penalty assessment, and reports the
width of the unresolved score bounds. Positive coverage of 1 can coexist with
unassessed penalties; `SCORED` alone does not mean every applicable leaf was
assessed. `fully_assessed_point_score` requires valid hard gates, complete
positive and penalty assessment, `SCORED` status, and equal lower/upper bounds.

Each assessment section also lists `unassessed_items`: the saved question ID,
module ID and saved assessment weight for each `CANNOT_ASSESS` criterion, in report
order. Older reports without those IDs retain null identifiers. Use this trace
to locate the original criterion and evidence before deciding what information
is missing. It does not diagnose the cause, recommend an edit or change a verdict.
The listed weights are local assessment weights, not estimated score effects.

The threshold convention is inclusive (`score >= threshold`). `ROBUSTLY_MEETS`
means the lower bound meets it; `ROBUSTLY_BELOW` means the upper bound is below
it. An interval spanning the threshold is `UNRESOLVED`. This is a scalar-bounds
diagnostic: check eligibility and report status separately before acting.
For a historical report affected by the ladder limitation above, a separated
bound or threshold result is not a guaranteed conclusion about every possible
resolution of the unassessed verdicts.

To inspect saved HBQ-RS reports for one recognizable ladder-risk pattern, run
`python -m hbqrs.decision_readiness_advisory score.json --threshold 50`, optionally
adding `--compare other-score.json`. This recomputes the existing readiness
diagnostic and adds an advisory; it does not alter the reports or rescore them.
A potential match is not proof that a bound was violated, and no match does not
prove that a bound is valid. Missing or unsupported evidence is indeterminate.

Comparison reports `LEFT_ABOVE` or `RIGHT_ABOVE` only for compatible, eligible,
scored reports with strictly separated bounds. Overlapping or touching bounds
are inconclusive. Different visible scoring structures, policies, weights or
applicability make reports incomparable. These checks do not establish shared
judge, prompt or source conditions. Dynamic task contracts additionally require
`--comparison-context-sha256` with a caller-verified shared frozen-context digest;
the tool records that attestation without independently verifying it.

These bounds measure sensitivity to unassessed rubric verdicts. They are not
statistical confidence intervals, human-agreement evidence or permission to
promote a rubric candidate.

For worked public examples, see the [established-rubric repeatability study](https://github.com/HaileyStorm/Creative-Writing-Rubrics/tree/b4ba4c5d2963040ffc6f26010de089e21331a0b4/evaluation-results/the-part-that-arrives-first-repeatability/established-v4), its [authorized source story](https://github.com/HaileyStorm/Creative-Writing-Rubrics/blob/b4ba4c5d2963040ffc6f26010de089e21331a0b4/evaluation-results/the-part-that-arrives-first-repeatability/source.md), and the sanitized [Gray Blood long-form comparison](https://github.com/HaileyStorm/Creative-Writing-Rubrics/tree/b4ba4c5d2963040ffc6f26010de089e21331a0b4/evaluation-results/gray-blood-ch1-6).

The [QPC24 V9 full-book rebaseline aggregate](https://github.com/HaileyStorm/Creative-Writing-Rubrics/tree/b4ba4c5d2963040ffc6f26010de089e21331a0b4/evaluation-results/hbq-gray-blood-full-book-qpc24-rebaseline-v9-public-result-v1) is work in progress: it reports all selected units without sampling, keeps bounds non-statistical, and makes no rubric promotion.

The [stopped Sol/TTCW development comparison](../evaluation-results/hbq-sol-ttcw-stopped-development-20261020/README.md) reports actual method coverage and existing expert-reference agreement. Its unequal, incomplete subsets cannot select a winning method. The [retained LAMP applicability diagnostic](../evaluation-results/hbq-lamp-applicability-development-20261020/README.md) separates complete response membership from binary assessment, inapplicability and unassessability; persistent NA alone does not establish a rubric defect.

The [retained LAMP ordinal development comparison](../evaluation-results/hbq-lamp-stopped-development-20261020/README.md) uses human preferences within passage triplets. It reports the lack of shared HBQ/comparator pairs and distinguishes order consistency from agreement with humans.

### Inspect completion-aware decision readiness

Use the optional Python API when a decision needs to consider every supported
resolution of a small number of unassessed or omitted verdicts. Supply the
original module objects, bundle and verdict records; saved score reports or
caller-supplied numeric intervals cannot establish this calculation.
Under the strict import policies, any supplied task contract must also satisfy
the shipped task-contract schema; malformed contracts raise an error before a
readiness decision is returned.

For direct score imports, `strict_import_v3` additionally validates any supplied
task contract against the shipped schema before compiling it, and records the
schema hash in the admission receipt. `strict_import_v1` and `strict_import_v2`
retain their historical verdict-admission behavior for reproducibility. This
checks structure, not whether evidence or quotations are grounded in the source.

Task contracts may opt into `contract_version: 2` for corrected instructions
on absence requirements: YES means the prohibited condition is absent, NO means
it is present, and insufficient evidence remains CANNOT_ASSESS. Version 1
retains its historical compiled guidance so saved prompts can be verified and
replayed. The version-specific schema hash is recorded by `strict_import_v3`;
automatic long-form route generation continues to use version 1. A versioned
instruction does not by itself verify a judgment or change old results.
Low-level historical compilation preserves legacy behavior for other version
values; schema-validated entrypoints, including `strict_import_v3`, reject
invalid or missing versions.

Given `modules`, `bundle` and an original bank `left_verdicts` whose artifact ID
is `left`, inspect an inclusive threshold (`score >= 40`):

```python
from hbqrs.completion_readiness import readiness

threshold_result = readiness(
    modules, bundle, left_verdicts,
    artifact_id="left", threshold=40, max_cases=243,
)
print(threshold_result["completion_readiness"]["relation"])
print(threshold_result["completion_readiness"]["bounds"])
```

The API recomputes the existing finite completion envelope using `NO`, `YES`
and `NOT_APPLICABLE` replacements, holding other verdicts and the task contract
fixed. `ROBUSTLY_MEETS` requires its lower endpoint to meet the threshold;
`ROBUSTLY_BELOW` requires its upper endpoint to fall below it. Otherwise the
relation is `UNRESOLVED`. For an invented four-question ladder fixture, the
historical upper bound is 35, while completion bounds are 25–45: the historical
threshold-40 result is `ROBUSTLY_BELOW`, but the completion result is
`UNRESOLVED`. This illustrates a mechanical failure mode, not its prevalence.

With another original bank `right_verdicts` whose artifact ID is `right`, compare
under the same supplied modules and bundle:

```python
from hbqrs.completion_readiness import comparison

pair_result = comparison(
    modules, bundle, left_verdicts, right_verdicts,
    left_artifact_id="left", right_artifact_id="right", max_cases=243,
)
print(pair_result["completion_comparison"]["relation"])
```

`LEFT_ABOVE` or `RIGHT_ABOVE` requires strict separation of the two completion
ranges. Overlapping or touching endpoints are `INCONCLUSIVE`. The two banks'
completions are considered independently; this does not model shared latent
evidence or establish a preference between authors or models.

The default maximum is 19,683 combinations **per bank**; `max_cases` may lower
that cap, so a pair may require up to twice the selected budget. This is a work
bound, not a time guarantee. `UNAVAILABLE` withholds decision bounds when a cap
is exceeded, any completion is not `SCORED`, or the historical report is not
`SCORED` or has invalid/unresolved hard gates. Unsupported inputs raise an
error. Strict import admission checks structure and declared evidence; it does
not ground references against source text or admit synthetic replacements as
new judgments.

The output retains `historical_report`, `historical_readiness` and, for pairs,
`historical_comparison` separately with their existing meanings. Pair comparison
keeps the existing report-visible compatibility checks, including scoring
context, weights and applicability. Those checks and shared arguments do not
authenticate judge, prompt or source conditions. The legacy comparison's frozen
context digest is a caller attestation; this API accepts no such digest and
leaves dynamic-task comparisons incomparable when that attestation is required.

These finite, fixed-verdict scorer bounds are not statistical confidence
intervals, calibrated model uncertainty, human-alignment evidence, promotion
criteria or authority for unattended acceptance. Historical scoring and runtime
defaults remain unchanged.

## Validate a supplied complete response bank offline

`hbqrs.response_validation.validate_response_bank` checks raw JSON responses
against supplied modules, a bundle, artifact/context text and an optional task
contract. It calls no judge and returns no score.

```python
from hbqrs.response_validation import validate_response_bank

# Each entry binds one requested batch to its unmodified raw response text.
# requested_batches must partition the entire compiled bank in runner role order.
result = validate_response_bank(
    modules, bundle, requested_batches,
    artifact_id="example", artifact_text=artifact_text,
    context_texts=context_texts, task_contract=task_contract,
)
print(result["membership_complete"], result["verdict_counts"])
```

Each batch has exactly `question_ids` (a nonempty list of strings) and
`response_text` (raw JSON text). Request IDs must cover every compiled question
once, ordered by hard gates, domains, penalties, then supplements; preserve
compiled order within each role. Verdicts inside a response may arrive in any
order and are returned in request order. Use raw text rather than parsed objects
so duplicate JSON keys remain detectable.

New runs, CLI validation and compilation, and this API reject unknown question
or group selector IDs by default (`exact_selector_ids_v1`). The lower-level
historical core remains permissive. Existing runs retain their recorded policy;
older runs without a policy resume with `historical_permissive_v1`. Explicit
historical mode preserves that behavior and must not be described as strict
selector validation. Native runs pinned to older runtime bytes require their
original runtime; this policy does not migrate those receipts.
For the frozen execution contract required by independent run verification,
copy the recorded policy as described in [Judging](judging.md).

Offline validation now emits a `supplied_complete_response_bank_v2` receipt
whose input digest includes the selector policy. To reproduce a prior v1 receipt
and digest, pass `selector_policy="historical_permissive_v1"` explicitly. That
option also retains historical permissive selector handling.

The API requires the existing canonical module, bundle and versioned task
schemas. It uses finite JSON parsing, the exact batch response schema, the
runner's evidence normalization without repairs, and `strict_import_v3`.
Exact quotes must occur contiguously in the supplied artifact or ordinary
context. References and summaries remain declarations: acceptance does not
verify their truth, location or sufficiency. Canonical `CANNOT_ASSESS` and
`NOT_APPLICABLE` values remain visible; complete membership does not imply all
questions received a binary assessment. NA requires its strict-import activation
reason; the current wire contract permits a blank CA note.

Malformed supplied data raises `ResponseBankValidationError`, with
`failure_type` and optional one-based `batch_number`, without echoing supplied
prose. Runtime/environment errors can still propagate. Successful results have
status `SEMANTICS_VALIDATED_ONLY`, normalized verdicts, counts and digests of the
supplied values, raw responses and derived schemas. These digests do not prove
what a judge received or authenticate provider/native execution, source identity,
applicability or quality. The API supplies no judge/run identity, repairs or
promotion decision. Scoring behavior is unchanged.

## Bias controls

For a retrospective or prospectively specified comparison with missing scalar
scores, `hbqrs.pairwise_bounds.pairwise_agreement_bounds` accepts one row per
planned item with `id`, `group`, `reference`, and `score`. Use `None` for an
unavailable reference or score and `within_groups=True` for within-group pairs.
The caller must establish provenance, eligibility and consistent score direction.
The function excludes missing or tied references from its denominator, assigns
half credit to observed score ties and allows each unresolved score pair 0–1
credit. It reports counts and relaxed outer bounds; because pairs share items,
those extrema need not be jointly attainable. Float endpoints are rounded
outward when needed to contain their exact rational values; a mathematically
zero-width bound may span adjacent floating-point values. The exact numerators
are recoverable from the reported counts. The default policy is
`reference_conditioned_pairwise_outer_bounds_v2`; pass the explicit policy
`reference_conditioned_pairwise_outer_bounds_v1` to reproduce historical
nearest-float endpoints, which can be slightly inward. Neither policy changes
the pair counts or the underlying exact rational bounds. An empty eligible denominator
returns null bounds. These bounds are conditional on available references; they
are not full-population bounds, confidence intervals, human validation or a
substitute for reporting missingness and the study's prespecified analysis.

Hide author and model identity. Shuffle candidate order. Do not reward length or rhetorical confidence unless a leaf asks for it. Keep user-taste overlays out of the craft total.

## What this is not

HBQ-RS does not claim human-agreement proof from syntax checks or a single uncalibrated model. Calibrate against a labeled set before treating deltas as significant.
