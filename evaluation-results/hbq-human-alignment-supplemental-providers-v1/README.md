# Supplemental HANNA provider study v1

This immutable external-work successor repeats the frozen HANNA v3 item, prompt, task-contract, question, and rendered-batch inputs with Grok 4.6 High and Nous DeepSeek V4 Flash Max. Nous Pro is conditional: its predeclared development-only macro-correlation trigger is checked once before later phases.

The GPT-5.6 Sol study remains the reference. This study publishes aggregated, prose-free results only. Its external work directory holds the authorized HANNA inputs and provider receipts; it is never committed here.

Run `prepare_provider.py` against a frozen GPT v3 work directory and pinned HANNA data, then run each provider's development phase. Create the immutable promotion gate and run every eligible provider's complete repeatability phase before confirmatory work. Later phases require `--data-dir`, allowing the gate to replay pinned-data analysis before another remote request. `analyze_study.py` validates ratings/model metadata, the checkpoint-v4 runner, byte-identical inputs and prompts, provider receipts, fresh sessions, and the public-output privacy boundary before publishing a phase result.

Grok accepts up to its frozen worker maximum. Nous uses exactly one worker and should use `--timeout 600` (the runner rejects less than 420 seconds). Before a provider job starts, each invocation seals its provider, phase, worker count, timeout, frozen contract, HBQ runner, study wrapper, sibling analysis/gate, and—on Nous—the canonical bridge/launcher bytes. Only an exact repeat can resume it, and analysis requires that record before publication.

Older external Grok and Nous output roots remain historical pre-hardening evidence. Do not backfill their invocation records; prepare a new external work directory for this runner version.
