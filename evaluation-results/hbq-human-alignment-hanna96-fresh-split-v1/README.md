# HANNA96 Fresh Residual Split v1

This package exposes only a score-blind 32-item validation split from the 57 HANNA prompt groups not present in Fresh88. Sixteen validation groups are open. The remaining 16 future-confirmation and 25 reserve groups are locally held as `privately_frozen_unopened`: their source groups, stories, prompts, targets, and partition seed do not appear in this public projection.

The source is the MIT-licensed `hanna_stories_annotations.csv` at upstream commit `282f27536a5d05ad4ce14298abcd70c45668fed2`, pinned to 13,219,167 bytes and SHA-256 `ef59054d27fa32def06cfdc57243b1dd09c7e71f40b6d9d43fecfbf60e59026b`. Its Git blob object ID is SHA-1 `2eec3bbf5b1363a998dbf73199228e4fe13405ca`; it is not labeled as SHA-256.

Validation groups are ranked with `sha256('hanna96-fresh-split-v1|202608311|' + prompt_group_id)`. Within each open group, non-Human story IDs are independently ranked with that seed, group ID, and story ID; the first two are selected before any six-dimension annotation aggregation. Each selected target is the mean of exactly three finite annotations. The private freeze uses a separately generated local cryptographic seed and is committed publicly only by SHA-256.

Rebuild into a new target only:

```powershell
python study.py --freeze-private --source $HANNA_CSV --private-root $PRIVATE_ROOT
python study.py --build-public --source $HANNA_CSV --private-root $PRIVATE_ROOT --output .\new-manifest.json
```

Verify the tracked materialization against the exact source:

```powershell
python study.py --verify --source $HANNA_CSV --private-root $PRIVATE_ROOT
```

The tracked `manifest.json` is canonical JSON with SHA-256 `ca5adea2288d9c01ddf3aeb0c6239ac2c550d26095a2c66a928d90511f4afb16`; its private-freeze commitment is `442c564da1933b5e5b444046748db88dfce6725b23a87bba099e524167102410`. This is source/split provenance only: it makes no provider calls and contains no DSPy, Optuna, runtime, or alignment-result claim.
