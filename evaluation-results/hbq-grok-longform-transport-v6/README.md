# Grok longform transport v6

This is a named, source-pinned transport descendant for the frozen P4 full-source prompts. It changes no installed broker, adapter, armer, route, gate, or predecessor evidence. It does not establish model context capacity, native longform delivery, absence of model-side truncation, or whole-body reading.

`derived.py` checks all three predecessor SHA-256 pins before executing a finite AST projection in unique private modules. It replaces three broker constants, two adapter constants, seven broker adapter-version comparisons, one armer audit-version constant, one armer broker import, and one explicit adapter tools-root command binding. Unexpected transformation counts fail closed. Canonical module names and objects are never replaced. The profile commitment records loader bytes, source bytes, transformation counts, contract, and effective AST hashes. The two executable entry files pin the loader before importing it.

The v6 contract caps raw prompt UTF-8, canonical stdin, prompt-history line, and first-user update line independently at 400,000 bytes. Aggregate updates are bounded at 600,000 bytes. Other update lines, summary, stdout, and stderr retain 65,536-byte bounds. JSON escaping can exceed a bound even when raw UTF-8 fits; there is no truncation or summary substitution. The entry point requires the exact canonical v6 contract, one turn, and 900 seconds. Image mode is incompatible with this contract. Existing native identity, time, prompt, final-answer, schema, paid-route, tool, and turn checks remain in force, including the predecessor's explicit single-terminal-LF prompt-history equivalence.

Qualification is read-only and prints aggregate dimensions and commitments:

```powershell
python -B evaluation-results/hbq-grok-longform-transport-v6/derived.py --tools-root <installed-tools-root> --qualify-manifest <P4-frozen-manifest> --manifest-sha256 d0cb6589924a4900b123206f40595035a6d792c623bac1c8303de9d95bac1ac4
```

The first-user dimension uses a synthetic permitted-structure wrapper with maximum bounded identifier length and counter width; it is not an observed native update. All 232 frozen prompt artifacts must match their committed hashes and sizes. No prose, human labels, or model requests are printed or sent.

For later root-owned execution, `load_broker().Broker` supplies the projected shared request/receipt implementation. Callers must bind `profile_commitment()`, entry-file hashes, exact route, source manifest, request/schema, account and logical slot before contact. The P4 continuation collector is a separate next implementation; this tree does not reserve or resend any P4 slot. Existing completed/native-failure evidence remains immutable. Slot 2 needs its exact positive no-contact proof joined by a named descendant; absence of an attempt file alone does not permit resending.

Arming is an explicit state-changing operation, not qualification:

```powershell
python -B evaluation-results/hbq-grok-longform-transport-v6/arm.py --tools-root <installed-tools-root> --root <fresh-v6-broker-root> --subscription-evidence <fresh-reviewed-evidence> --grok-exe <exact-installed-grok-executable>
```

The wrapper fixes one turn, 900 seconds, no images and host concurrency 10. Collection still requires one worker. It rejects historical standing/incident geometry and accepts only the predecessor's reviewed schema-1 evidence profiles. It retains shared host-wide stop/revocation and slot handling. The shared gate contract includes the transport dimensions: all v5 slots must be quiescent before a root-owned v6 arm, and old v5 routes then require reauthorization. A separate broker root does not bypass this constraint; do not supply a separate production host-gate database.

The collector remains responsible for the campaign cutoff `2026-10-16T05:40:00Z` with a 900-second margin, STOP before the next contact, retaining the settling current call, zero automatic retries, and no ambiguous resend. Arming alone supplies none of those study decisions. Root must review/freeze the continuation, disclose the exact outbound full-source artifacts, qualify native delivery, and arm with current reviewed zero-charge evidence before execution.
