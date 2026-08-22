# Batch-curve Codex remainder v3

This successor preserves the one failed, unscored v2 epoch-one preflight as
logical preflight attempt 1. Its schema lacked `type: boolean` for `ready`, so
Codex rejected it before scoring. The immutable v2 public and private roots
are bound by exact path, tree, and semantic checks. V3's first new preflight is
logical attempt 2 and uses the corrected strict schema. The 47 sealed scored
partitions remain unchanged.
