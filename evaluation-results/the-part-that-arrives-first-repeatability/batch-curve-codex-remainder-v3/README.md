# Batch-curve Codex remainder v3

This archived successor design preserves the one failed, unscored v2 epoch-one
preflight as logical preflight attempt 1. Its schema lacked `type: boolean` for
`ready`, so Codex rejected it before scoring. The immutable v2 public and
private roots remain recorded by exact path, tree, and semantic checks. V3
copied v2's stale multi-asset current-stack bindings and therefore deliberately
fails closed from a clean checkout; it has no currently executable recovery
path. The 47 sealed scored partitions remain unchanged.
