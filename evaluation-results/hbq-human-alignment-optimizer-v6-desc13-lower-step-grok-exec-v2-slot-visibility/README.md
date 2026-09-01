# Lower-step Grok execution v2: Windows slot visibility

V2 pins the complete committed V1 package and changes only global slot
observation. A loser that sees an existing slot file now treats verified
Windows sharing or lock access errors, or a same-file size/mtime drift while
the winner writes, as a bounded retry. Stable malformed slot content is still
rejected. Every lifecycle entry validates V2's source inventory and contract,
then the complete pinned V1 lineage, before dispatch. The ten-slot limit,
fresh-root rule, no-resend policy, and V1 callback-time prepared-artifact guard
remain inherited.

The failed V1 root is immutable terminal evidence. V2 never resumes or projects
it; execution requires a separately prepared fresh root.
