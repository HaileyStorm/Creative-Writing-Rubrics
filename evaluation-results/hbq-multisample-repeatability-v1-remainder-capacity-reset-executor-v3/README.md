# Multisample capacity-reset executor

This v3 package is the executable successor to the pushed v2 contact-free handoff. It binds that exact v2 revision, its 153-cell schedule, and the reconstructed 33-file v1 executor core before it can send one cell.

Each invocation dispatches at most the next unfinished cell. It records a fresh native capacity proof and an attempt intent before contact. An unresolved intent, quota failure, uncertain provider result, session collision, or source/runtime drift stops the run; it never resends or selects a different cell. The frozen inner runner remains responsible for its own fixed protocol semantics.

The route is Codex CLI with GPT-5.6 Sol/high only. It uses no paid API and no human judgment. `--dry-run` is offline; a real send additionally requires `--allow-remote` and a current capacity proof.
