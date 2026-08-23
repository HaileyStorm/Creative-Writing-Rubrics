# HBQ-RS 1.2.0: Hierarchical Binary-Question Rubric Stack

## Status and purpose

HBQ-RS is a composable evaluation format for creative-generation systems. It converts broad rubrics into a hierarchy whose scored leaves are independently answerable binary questions. The format is designed for AI judges, human review, automated candidate selection, revision diagnosis, and mixed text–image–audio projects.

HBQ-RS adopts the central result of BinEval: broad judgments become more interpretable and discriminating when decomposed into small yes/no questions. It does **not** assume that unlimited decomposition is beneficial. Holistic artistic success, taste, and other genuinely gestalt judgments remain controlled threshold ladders rather than being atomized into fake objectivity.

## 1. Composition model

An execution compiles a **rubric stack** rather than selecting a monolithic rubric. The standard order is:

1. Dynamic task and hard-constraint questions.
2. Universal quality modules.
3. Relevant craft modules.
4. Artifact or form module.
5. Scope overlay.
6. Genre, audience, tone, and user-taste modifiers.
7. Procedure module.
8. Project/canon fidelity modules.
9. User additions, replacements, disables, or reweights.
10. One holistic artistic-success ladder.
11. Bounded anti-pattern penalties.

A criterion has one scoring owner. Overlays alter activation, interpretation, evidence scope, or weight; they do not create a second score for the same proposition.

## 2. Node types

A rubric module is a recursive tree containing:

- `group` nodes, which organize related questions and may carry a scoring mode or cap.
- `question` leaves, which carry the actual binary decision.

Every question leaf includes a stable ID, a globally owned `criterion_key`, positive wording, weight, type, severity, activation condition, and evidence policy.

### Question types

- `hard_gate`: a failed objective, atomic, explicitly non-negotiable requirement from the frozen task contract invalidates the output for the requested operation, regardless of artistic merit.
- `scored`: contributes to a weighted quality domain.
- `subjective_threshold`: contributes to a small cumulative holistic ladder.
- `diagnostic`: reported but excluded from the quality total unless a bundle explicitly promotes it.

### Verdict states

- `YES`: the positive criterion is satisfied.
- `NO`: it is not satisfied.
- `NOT_APPLICABLE`: the declared condition does not activate for this artifact.
- `CANNOT_ASSESS`: the criterion is relevant, but the supplied evidence is insufficient.

`NOT_APPLICABLE` and `CANNOT_ASSESS` are control states, not softer quality scores.

## 3. Evidence protocol

The judge returns a verdict, confidence, concise note, and one or more artifact references when required. A reference may be a line range, paragraph ID, scene ID, timestamp, image region, panel ID, audio segment, source document, or project-record ID. The evaluator should not emit private chain-of-thought. Evidence must support the verdict rather than merely repeat the criterion.

## 4. Scoring

Let a domain `d` be worth `P_d` points. Each selected applicable question `i` has leaf weight `w_i`, bundle-component multiplier `m_i`, and ancestor-group multiplier product `g_i`. For assessed questions, `x_i = 1` for YES and `0` for NO.

```text
observed_domain_d = P_d × Σ(w_i m_i g_i x_i) / Σ(w_i m_i g_i), over YES/NO leaves
```

Questions marked `NOT_APPLICABLE` are removed. Questions marked `CANNOT_ASSESS` create an interval:

```text
lower_domain_d = P_d × passed_weight / applicable_weight
upper_domain_d = P_d × (passed_weight + unassessed_weight) / applicable_weight
coverage_d = assessed_weight / applicable_weight
```

The observed score is reported only with coverage. Below the bundle threshold it is `PROVISIONAL`; it must not drive unattended acceptance.
If no point-bearing question is assessable, the observed score is `null` and the status is likewise provisional rather than `SCORED`.

### Penalties

Penalty questions are also positive. A NO verdict activates a proportional deduction up to the bundle cap `C_g`:

```text
observed_penalty_g = C_g × failed_assessed_weight / assessed_applicable_weight
```

The report also gives a penalty interval when questions are unassessed. Final score is bounded to 0–100:

```text
final_observed = max(0, base_observed − observed_penalties)
final_lower    = max(0, base_lower − penalty_upper)
final_upper    = max(0, base_upper − penalty_lower)
```

Hard-gate status is reported separately as `VALID`, `INVALID`, or `UNRESOLVED`.

Author preferences, aesthetic targets, revision priorities, and inferred goals are never hard gates. They may receive explicit weight in the task domain, but failure lowers the quality result rather than invalidating the artifact. Broad catch-all questions such as “does it satisfy every inclusion?” are diagnostic only; binding requirements must be split into independently answerable leaves before judging.

### Scope composition

A score belongs to one exact evaluation scope: artifact bytes, scope-correct bundle, materialized weight profile, task contract, question set, and verdicts. Within a hierarchy, evaluate that scope once and reuse its result in every view. Do not recompute a chapter merely because it appears beneath a manuscript card.

Parent scores are not reconstructed by averaging child scores. A chapter score may include chapter opening/closure and across-scene criteria that no individual scene can answer; penalty caps, conditional activation, coverage, and hard gates also make normalized child scores non-associative. Scene results therefore remain diagnostic children unless an explicit, disclosed composite profile says otherwise.

Two runs produce the same deterministic score only when their materialized scoring inputs and verdicts are the same. A fresh model call with different map context is a new evaluation, even if the visible prose is identical.

## 5. Controlled subjective assessment

The default holistic module is worth eight points and uses four cumulative thresholds worth two points each:

1. Does the artifact work at all as the intended kind of thing?
2. Is it genuinely effective rather than merely functional?
3. Is it worth keeping, using, sharing, or developing?
4. Is it exceptional relative to strong work of its type?

A higher threshold can pass only when all lower thresholds pass. This gives artistic gestalt enough influence to matter while preventing taste from swamping the analytic evidence.

## 6. Excerpts and incomplete artifacts

A flagged excerpt is judged for visible local craft and contribution to the supplied larger context. It is not penalized for absent whole-work resolution, and unavailable whole-work questions become `CANNOT_ASSESS` or `NOT_APPLICABLE`. A partial artifact presented as complete, or one whose partial status is omitted, may receive the bounded unflagged-incomplete penalty. Accidental truncation remains a defect at any scope.

## 7. Length and form fit

An exact word, line, duration, or format constraint is a hard gate only when it is explicitly non-negotiable, objectively verifiable, and frozen in the task contract before judging. Otherwise, length is a positive fit criterion: enough space for the artifact's actual creative load, no padding to hit a target, and no underbuilding disguised as economy. The applicable form and operation determine the standard.

## 8. Long-form protocol

A manuscript, collection, visual sequence, or long narration requires hierarchical evaluation:

- construct a whole-work map;
- track characters, state, chronology, promises, motifs, and threads;
- evaluate opening and ending against one another;
- evaluate every substantive local unit by default, or explicitly declare a bounded stratified sample;
- test recurring patterns and distant dependencies;
- separate systemic defects from isolated imperfections;
- report retrieval and context limitations.

A full-work score is never the unqualified arithmetic mean of chapter or segment grades.

## 9. Pairwise selection

Strong finalists are first evaluated independently. Pairwise comparison then examines only material tradeoffs. Candidate order must be swapped or randomized, labels and irrelevant metadata should be hidden, and ties should remain ties when evidence does not justify arbitrary precision.

## 10. Dynamic task questions

The stable registry supplies craft and workflow knowledge. Before candidate judging, the brief and declared context are compiled into a frozen task contract with two scored/control surfaces:

- `weighted_goals`: atomic author goals and preferences that contribute to the task domain without affecting eligibility;
- `binding_requirements`: atomic, objective, explicitly non-negotiable constraints that become hard gates.

Context, background, and priorities remain available to the evaluator but are not silently promoted. Every dynamic question must be traceable to an exact prompt or source excerpt, condition-aware, observable, deduplicated against the registry, and validated before use. The system must not let a judge invent preferences or requirements after seeing candidate outputs.

## 11. Strict AI-output judging prefix

The evaluated artifact is AI-generated. The judge should be exacting without becoming hostile or arbitrary. It should use the full verdict range, reserve high marks for demonstrated excellence, judge execution rather than imagined intent, deny benefit of the doubt where evidence is absent, and avoid flattering surface polish. It must also avoid inventing defects, treating deliberate ambiguity as confusion, or preferring verbosity, ornament, moral conformity, or familiar style for their own sake.

## 12. Serialization

Canonical machine formats are JSON and JSONL. YAML is provided for human editing. The schemas in `schema/` define modules, bundles, task contracts, route selection, strict judge responses, verdicts, diagnostics, score reports, and long-form reports. Stable registry IDs and versions are mandatory; displayed titles may change without breaking references.
