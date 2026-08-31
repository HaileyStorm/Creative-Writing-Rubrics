# Broader Grok development execution v3

V3 pins V2 commit `3611a9dcba2df161b8e3fa89158c0c0b30b70bcf`.  Before a wave
fans out, it loads the pinned route/broker path and validates the current Grok
route exactly once, then gives every cell that frozen validated route result.
The ten-slot native execution gate is unchanged and remains concurrent.

The immutable partial V2 root is excluded without score inspection or
projection. V3 accepts only a fresh root and requires a complete new 35-cell
execution.
