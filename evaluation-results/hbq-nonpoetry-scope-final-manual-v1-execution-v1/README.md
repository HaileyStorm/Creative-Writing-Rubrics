# Final S2 manual execution successor

This frozen successor binds the exact private controller contract for the
four-fixture baseline/candidate comparison at commit
`09b403a6673645fa99efffebfbf24af7a986d190`. It is unexecuted. The only
future route is Codex `gpt-5.6-sol` at `high`, one leaf per call, with at most
three cumulative attempts per slot (72 sends maximum).

The private controller creates the 24-slot schedule, arm-specific private
registries, immutable inputs, preexecution disclosure, zero-charge
acknowledgement, and receipts. `--dry-run` remains provider-free. Execution is
not an authority to promote anything: settlement verifies the private oracle
and exact candidate gate offline, publishes only an aggregate, and returns
`HOLDOUT_ELIGIBLE_ON_SUCCESS` or `NO_GO_DSPY_ELIGIBLE_ONLY`. Promotion is
always `none`.
