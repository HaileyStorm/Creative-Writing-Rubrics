# Premise-scale ownership execution v1

This is the separately frozen, zero-paid execution successor for the public
synthetic development screen at `95a86b8353b4d27c85914d4258e4da33d080f9d7`.
It contains no result, real-text payload, expected verdict ledger, raw response,
or provider transcript. Preparation writes the immutable private schedule outside
the checkout; dry-run renders and commits all 72 ordinary singleton CWR prompts
without contacting a provider. There are exactly 72 logical slots; each has at
most three cumulative replacement attempts, so the route permits at most 216
provider sends. Execution is available only with both explicit remote and
owner-attested subscription-route acknowledgements. `--execute` starts only
slots with no prior provider attempts; `--resume` continues the prepared
schedule without adding logical votes.

The public synthetic corpus is the only content a provider may receive. Case,
pair, slot, repeat, expected-verdict, and oracle metadata remain only in the
private schedule. The sealed real-text holdout is neither read nor addressable by
this successor.

The current-wording screen can only report `PASS_NO_CHANGE` if all 72 slots are
accepted and grounded, and each of the 20 scored cells (60 slots: YES, NO, and
CANNOT_ASSESS) matches three times. The four NOT_APPLICABLE cells (12 slots)
are completed diagnostic controls and are not pass-scored. It never promotes
prompt or rubric changes. A later clarification package
is eligible only under the frozen predecessor rule and is barred by repeated
same-premise/same-verdict evidence that instead signals duplication.
