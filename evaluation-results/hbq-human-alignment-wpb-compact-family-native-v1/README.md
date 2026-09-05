# WPB compact-family native executor v1

This package materializes and settles the 129 endpoint-neutral WPB compact-family tasks from the immutable r3 freeze: 105 TRAIN and 24 DEV pairs. It is a thin transport boundary around the reviewed compact core; it does not change its coarse `core` / `craft` / `form` proxy, local target handling, TRAIN-only Optuna fit, DEV selection, or closed confirmation partition.

`prepare_all` is provider-free. It composes the pinned V16 native Grok or Sol lifecycle and writes its exact task-payload, route-proof, acknowledgement, and prepared-state commitments while reporting zero contacts and process launches. The local targets, category, source model, preferred side, and source scores are never copied into a prepared provider cell. The Sol lifecycle carries a fixed all-zero V16 transport sentinel only; it is not a WPB label and is not outbound.

`execute_one` and `execute_wave` require explicit `allow_remote=True`. They use the V16 native defaults for Grok and Sol; optional runner and broker/call overrides exist only for controlled tests. A wave keeps at most ten calls in flight. The first raised error, non-success terminal state, or missing terminal receipt stops scheduling every queued cell; already-started calls settle without a process kill, and their artifacts remain for inspection. The inherited native lifecycle reserves a cell before dispatch, rejects a resend, and binds terminal receipts to the endpoint, payload, route proof, acknowledgement, and native response.

`report` independently reloads the pinned core and r3 freeze, re-admits every receipt, and passes endpoint-separated measurements to the compact analyzer. It does not pool Grok and Sol, fit a runtime profile, open confirmation, or claim native admission from preparation alone.

No command-line entry point is provided. A reviewed caller owns route refresh, outbound disclosure, and the explicit decision to make provider contact.
