# HBQ refusal and terminal singleton matrix v1

This is a provider-free, public-synthetic exercise of six terminal-state
classifications for one selected HBQ-RS leaf:
`core.substantive_task_engagement_true_non_refusal.no_refusal`.

It injects nine typed attempts through `hbqrs.runner.run_judge`, then reduces
the runner's real rejected-attempt and response-checkpoint artifacts. It does
not contact a provider, make a general claim about real-world refusals, change
the production runner, or amend the rubric. Its contract binds the canonical
`fb77e8a` Git blobs, not CRLF-sensitive working-tree bytes.

The six fixed scenarios are one accepted response, exhausted
refusal/deflection, exhausted blank-quote/schema failure, retryable transport
followed by acceptance, nonretryable provider stop, and a started-but-unsettled
attempt that is never automatically resent. Every slot records only public,
path-free counts and hashes.

The injected nine-attempt matrix and `python study.py verify` command are
historical/frozen-checkout-only: run them only with the exact `fb77e8a`
checkout bindings. The current checkout intentionally fails closed because
its runner and rubric inputs have advanced. `python study.py write
--output result.json` likewise describes only that frozen historical exercise.

This package does not define current refusal semantics. In the current runner,
unstructured refusal text in ordinary response content is a schema/quote
validation failure, while `model_refusal` is recognized only from the
provider's structured `message.refusal` field (under the opted-in refusal lifecycle
policy). Current-runner tests own that distinction.

`PASS_MATRIX` authorizes only Sol review and a separately designed production
exercise; it never promotes a schema or runtime change.
