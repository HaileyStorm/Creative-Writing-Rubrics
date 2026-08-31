# Fresh96 Sol validation execution v1

This is a thin, two-lane wrapper around the already-confirmed tool-free Sol lifecycle. It accepts only a fresh schedule root emitted by `hbq-human-alignment-hanna96-validation-freeze-v1`; it transmits each `payload_base64` byte sequence unchanged.

`prepare_all` creates 64 local-first prepared roots with no provider contact. `execute_wave` requires an explicit remote opt-in, a currently valid zero-charge `gpt-5.6-sol` high route, and has no fallback or resend path. A process-launch ambiguity is terminal. `write_projection_set` creates one fresh canonical Sol projection file for the paired analyzer; it retains original freeze cell IDs and every required schedule binding. `replay_projection_set` deterministically checks that persisted file against the completed lifecycle roots without contacting a provider. `reconcile_all` only reports/rejects terminal ambiguity and never requeues work.

Its output is endpoint-specific measurement material for the paired Fresh96 analyzer, not candidate selection, a pooled endpoint conclusion, a promotion, a runtime rule, or a generalization claim.
