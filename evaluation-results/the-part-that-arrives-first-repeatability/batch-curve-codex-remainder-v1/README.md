# Batch-curve Codex remainder v1

This is a successor plan, not an in-place resume and not a live executor. It
preserves the closed `ae23440-r1` run: 35 cells completed, while cell 36 (size
4, repetition 3) accepted batches 1–31 before all three attempts at batch 32
were rejected for quota. The successor schedules only batches 32–45 for that
cell plus the three never-started cells.

It can prepare fresh, disjoint roots without contacting a provider. A later
live executor must first record an explicit current quota preflight after
2026-08-27 19:21 -06:00. This package deliberately provides no provider-call
path, so preparation cannot consume quota or duplicate an accepted batch.
