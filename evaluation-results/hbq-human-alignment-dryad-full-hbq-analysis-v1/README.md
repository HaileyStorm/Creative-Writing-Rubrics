# Dryad full-HBQ analysis preregistration

This freezes the comparison before model measurement. The co-primary human targets are the authors' separate novelty and usefulness indices, each built from three complete blinded ratings. The model score is the canonical full 178-question short-story rubric's observed final score. All twelve source axes will also be reported separately; they are not averaged into a new human score or mapped onto selected leaves.

The fixed 176 TRAIN stories support a bounded 128-trial search over nine built-in domain-weight multipliers. The canonical all-one baseline is trial zero. DEV remains a 60-story comparison of that frozen TRAIN winner against baseline, with paired story bootstrap uncertainty and explicit failure for undefined replicates. A relative gain cannot disguise weak absolute alignment. The same candidate is checked on independent Sol judgments of unchanged judge-payload bytes; endpoint-specific system and transport metadata remain separate. Nothing here releases confirmation or promotes weights into runtime policy.

`source.py` only prepares and verifies local exact-rational human targets. It checks the immutable CSV, split, and parent provenance hashes; skips confirmation before interpreting rating values; and writes opaque TRAIN/DEV targets without story text, source IDs, evaluator IDs, condition, or topic. These files remain local and are not published. Creation requires committed generator and protocol bytes, and verification binds their recorded commit. This target packet is not model evidence or an implemented optimizer.

```text
python source.py prepare --ratings-path AUDITED_V2_CSV --freeze-root PARENT_FREEZE --output-root NEW_LOCAL_TARGET_ROOT
python source.py verify --ratings-path AUDITED_V2_CSV --freeze-root PARENT_FREEZE --output-root LOCAL_TARGET_ROOT
```

`qualification.json` fixes three label-independent TRAIN stories, three complete passes per story, and batch sizes 8 and 32. It requires all 261 planned native requests and compares all repeated-pass pairings; no sampled leaves or favorable-pass selection. Passing its engineering tolerances would support only the exact-stack operational cap, not accuracy or generalization. Qualification output cannot replace later fresh alignment measurements. The current empirical cap is null.

The protocol records current working-tree runtime hashes, including inherited CRLF/mixed representations. It grants no provider authority. The actual study launcher, deterministic analyzer and trial recomputation, exact runtime admission, reviewed bounded cohorts, and fresh shared allowance/arming must be completed before live execution. Historical WPB and V17 terminal samples remain excluded from automatic resend. No model-alignment result is claimed here.

[target-freeze.json](target-freeze.json) records the completed local target preparation: 176 TRAIN stories from 2,116 ratings and 60 DEV stories from 720 ratings. Both indices and all twelve axis means matched an independent exact-rational recomputation, and committed-source verification reproduced the target files byte-for-byte. Only counts and commitments are published.
