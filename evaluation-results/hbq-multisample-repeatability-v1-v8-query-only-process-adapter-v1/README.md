# V8 query-only process adapter v1

This default-off adapter changes only the loaded frozen target's `_pid_is_dead` function. On Windows it uses `OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION)` and `GetExitCodeProcess`; it never probes with `os.kill`. Absent/exited returns true. Live, reused, inaccessible, malformed, and unknown PIDs return false.

`prepare_operational_binding` is provider-free and writes a fresh supplemental binding. It does not run V8 preflight, create a guard intent, or authorize remote execution. Frozen V8 and historical wrappers remain provenance; remove this adapter only when a reviewed successor adopts the safe helper.

Use only this adapter's gated `preflight_one` or `dispatch_one` with a verified supplemental binding and `allow_remote=True`. Direct use of the standalone frozen guard remains unsafe and is prohibited by this continuation procedure.
