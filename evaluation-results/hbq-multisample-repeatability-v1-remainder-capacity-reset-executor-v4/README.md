# Multisample capacity-reset executor v4

V4 preserves the failed v3 root as immutable pre-dispatch evidence: its claim, two sequence-178 journal rows, proof, and zero-run state are never resumed. It starts sequence 178 anew in a fresh root, validates the pushed v3 provenance, and calls the actual successor-v1 owner for both revalidation and dispatch.

It sends at most one contiguous cell after a current native capacity proof and an exclusive local claim. A dangling intent, quota result, uncertain output, drift, or session collision stops without resend. No paid API or human judgment is used.
