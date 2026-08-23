# Free-verse repetition treatment execution successor

This unexecuted, development-only successor binds the r3 private controller
for the four-fixture, same-fixture A/B screen frozen at CWR commit
`76023dff13558f024fefb38cbd59ab45ae8682ec`. It schedules exactly 24
singleton calls: current and candidate wording across four fixtures and three
repetitions.

`--dry-run` renders and freezes the private inputs, disclosure, and prompt
pair checks without contacting a provider. `--execute` is deliberately
separate: it permits only Codex `gpt-5.6-sol` at `high`, with a zero-
incremental-charge owner acknowledgement, a single physical attempt for each
slot, and no resume path. Paid APIs and fallbacks are forbidden.

Settlement consumes terminal sidecar v1 evidence, keeps the original private
settlement write-once, and creates an aggregate-only public result. A passing
gate authorizes only a later disjoint holdout; it never promotes a prompt,
rubric, leaf, owner, split, or weight.
