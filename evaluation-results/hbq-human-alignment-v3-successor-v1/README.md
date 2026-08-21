# HANNA v3 successor, fresh 88

The historical verified-54/bridge route is disabled: the authoritative replay receipt is rejected.  Advancement requires a versioned external fresh-run contract, one genuine raw binary run directory for each frozen scheduled item, and a re-verification matrix. Caller summaries and projections are not evidence.

`fresh88-execution-contract.json` is created outside this package beside the frozen work. It binds all 88 item IDs, order, origins, run paths, item artifact/context/task bindings, and the registry, bundle, prompts, schema, provider/model/reasoning, execution, and weights consumed by `hbqrs.run_verify`.

The matrix is atomically sealed only after all 88 raw runs verify and every accepted or rejected session hash is unique study-wide. Calibration remains unavailable until an empirical comparison exists. No completed fresh-88 raw data is shipped here.

Prepare (no provider call):
`$env:PYTHONPATH='src'; python evaluation-results/hbq-human-alignment-v3-successor-v1/prepare_fresh.py C:\Users\Haile\Documents\cwr-hanna-successor-fresh88-freeze-v3 C:\Users\Haile\Documents\cwr-human-reference-v3-d9038f1\inputs <work> <artifacts>`.
Use `--dry-run` to validate and print `88` without writing. Then run `$env:PYTHONPATH='src'; python evaluation-results/hbq-human-alignment-v3-successor-v1/run_fresh.py <freeze> <work> <artifacts>`; this is the only command which can contact Codex.
