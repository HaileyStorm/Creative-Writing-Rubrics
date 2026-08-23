# Premise scale ownership v1

This is a frozen, public, synthetic, development-only screen for the lexical
overlap between `artifact.support.premise_story_seed.extensibility` and
`op.ideation.premise_stress_test.scale`. It neither asserts duplication nor
changes a rubric. The current production judge prefix and binary prompt are
bound unchanged. `run.py` only verifies or renders its 72 planned slots; it has
no provider-execution mode.

The production `hbq_judge_response` schema is bound from CWR directly; this
package intentionally carries no parallel response schema. Provider responses
remain production-shaped, while slot identity and expected labels stay in a
separate local ledger projection.

The corpus has six matched context-carrier perturbations. Each pair has isolated
and composite carriers with the same premise, scope, activation, targets, and
oracle verdicts; the composite carrier only adds a matched context note. Every
artifact independently declares its artifact and operation target length/form
and exposes named evidence sections. Every artifact is screened against both
leaves, one leaf per request, three times. Typed evidence may cite any permitted
section. Cross-leaf section or span overlap is recorded as an outcome, not
rejected by construction.

All applicable and control cells require three grounded, typed-evidence matches
to their declared expected verdict. `NOT_APPLICABLE` is completed but unscored;
`CANNOT_ASSESS` denotes coverage uncertainty. A missing or ambiguous slot is
`INCOMPLETE`. A single clarification successor can be frozen only after the
whole screen settles, two independent pair types repeat the same scope/control
error in at least two of three runs, and an independent Sol review attributes
the error to one missing rendering rule. Same-verdict, same-premise-evidence
behavior is instead a rubric or route duplication signal and bars clarification.

The real-text payload is absent from this public package. Its aggregate-only
public commitment is present and hash-bound: two openly licensed Blender short-
film premises are sealed from evaluation as positive realism controls, with no
expected verdicts. The current-wording diagnostic cannot access them; any later
treatment, optimizer, or confirmation requires a separately frozen execution
successor and explicit holdout-opening gate. No prompt, rubric, leaf, ownership,
split, or weight promotion is authorized here.
