# Supplemental HANNA provider study v1

This is an immutable, external-work successor that repeats the exact frozen HANNA v3 item, prompt, task-contract, question, and rendered-batch inputs with Grok 4.6 High and Nous DeepSeek V4 Flash Max. Nous Pro is not a default arm: its predeclared development-only macro-correlation trigger is checked once before the later phases.

The primary GPT-5.6 Sol study remains the reference protocol. This study publishes only aggregated, prose-free results. Its external work directory holds the already-authorized HANNA inputs and provider receipts; it is never committed here.

Run `prepare_provider.py` against an existing frozen GPT v3 work directory and its pinned HANNA data directory, then run every provider's development phase. Create the immutable promotion gate, then run every eligible provider's complete repeatability phase before any confirmatory work. Both later runner phases require `--data-dir`, so the gate can replay the pinned-data analysis before another remote request. `analyze_study.py` reopens the pinned data and validates its ratings/model metadata, current checkpoint-v4 runner, byte-identical inputs/rendered prompts, provider-specific receipts, fresh sessions, and the public-output privacy boundary before it publishes a phase result.

Grok accepts up to its frozen worker maximum. Nous uses exactly one worker and should use `--timeout 600` (the runner rejects less than 420 seconds). Each invocation seals its provider, phase, worker count, timeout, frozen contract, HBQ runner, study wrapper, sibling analysis/gate, and Nous-only canonical bridge/launcher bytes before any provider job starts; only an exact repeat can resume it. Analysis requires that exact provider/phase record before publication.

Older external Grok and Nous output roots remain historical pre-hardening evidence. Do not backfill their invocation records; prepare a new external work directory for this runner version.
