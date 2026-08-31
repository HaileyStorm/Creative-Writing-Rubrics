# HANNA next-wave development optimizer v1

This provider-free package replays the completed 33-cell Grok scorer from its
persisted collector and roots, then runs a deterministic 198-trial Optuna 4.9.0
grid. The objective adds small worst-group, leave-one-group-out, and explicit
next-step planning penalties to equal-group MAE. Candidate 08 remains the
development winner in all 18 low-penalty settings: MAE 0.750 versus 0.926 for
the unchanged baseline, a 0.176 absolute (19%) reduction on these three groups.

That is not a general HANNA result. At deliberately strong robustness weights
outside the grid, the ranking reverses, which is useful evidence that the
three-group screen is too small for promotion. Native endpoint-contact
cardinality also remains unproven.

The replay, normalized prompt/profile bytes, materialization inputs, pinned
dependencies, frozen successor, and CSV enter through one admitted in-memory
snapshot. Full ancestry and reparse checks plus directory inventory, file
identity/inode, size, timestamp, and byte checks run before and after every
phase. The result and contract bind the privacy-safe snapshot commitment.
Every one of the 198 Optuna trial tuples is unique, covers the exact grid, and
has its params and objective value independently recomputed before the 18
setting winners are derived from those verified trials.

DSPy 3.3.1 is used concretely to construct and validate 11 `Example` records
and two `Signature` schemas for a next prompt/profile view. No `Predict`, LM,
provider, queue, confirmation, or held-out target is invoked, and the scorer
executor retains no runtime DSPy or Optuna import.

The next economical check is six Sol cells: candidate 08 and the unchanged
baseline on the same three development groups with prompt/profile and item
payload bytes unchanged from Grok. If direction holds, the next broader Grok
screen is candidate 08 plus four 5%-step descendants over one prechosen item
from each of the seven frozen development prompt groups (35 cells), followed
by a 21-cell sprinkled Sol check of baseline, candidate 08, and the Grok
development winner. Confirmation stays closed throughout.
