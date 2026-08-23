# S2 non-poetry scope treatment v1

This provider-free development package tests the smallest next S2 remedy. It
does not change the shared prompt or rubric. The sole candidate wording is for
`scope.passage.status`:

> When a passage is explicitly an excerpt or fragment, does the evaluation
> exempt it from whole-work completeness requirements?

The candidate retains the existing leaf ID, module/criterion owner, `YES` pass
answer, diagnostic type, severity, and weight. It compares 18 new passage
slots (six corrected current-wording calls plus 12 candidate-wording calls),
reuses only six byte-identical accepted current-wording passage calls, and adds
nine corrected non-passage diagnostics. Thus a later execution successor has
exactly 27 new singleton calls and six immutable reuse bindings.

The five fixture corrections distinguish a real performed hybrid transition,
activated modes with transition evidence withheld, an unsupported whole-work
critique extrapolation, an excerpt with an explicit positive evaluation
disposition, and an explicitly excerpted passage with an unknown completeness
disposition. A separate four-state holdout contract is sealed before execution;
its prose and private location are deliberately absent.

`run.py --dry-run` and `run.py --render-plan` are provider-free. No result can
promote a prompt, rubric, leaf, owner, split, or weight. A later private,
separately frozen execution successor must settle this treatment and receive
independent review before it may reveal the holdout.
