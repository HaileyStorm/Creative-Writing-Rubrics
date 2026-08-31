# Fresh96 validation: Grok execution v1

This versioned wrapper runs the 64-cell public Fresh96 validation schedule on the xAI Grok endpoint. It loads the sealed endpoint-neutral schedule, sends the schedule's decoded payload bytes unchanged, and leaves endpoint aggregation to a separate analyzer.

It pins the confirmed Grok lifecycle, requires an explicit live zero-charge route proof and authorization acknowledgement before preparation, uses at most ten concurrent cells, disables tools through that lifecycle, and permits neither fallback nor resend. A cell with an ambiguous post-launch outcome is terminal for the root and must be reconciled provider-free; native endpoint contact cardinality remains unproven unless a persisted native receipt establishes it.

The output is endpoint-specific measurement evidence only. It cannot select a profile, establish generalization, promote runtime behavior, or substitute for the independent Sol endpoint.

Provider-free preparation:

```powershell
python executor.py --prepare-all --output-root <fresh-output-root> --frozen-root <sealed-fresh96-root> --queue-root C:\Users\Haile\.codex\state\model-work-queue --authorization-acknowledgement-sha256 <authorized-ack-sha256>
```

Only after a fresh route arm and explicit authorization, launch the bounded wave with `--execute-wave --allow-remote`; then use `--finalize-collector` and `--replay-collector` locally.

After a complete collector replay, `--write-projection --collector-path <collector> --projection-output <fresh-grok.json>` emits the analyzer-compatible `grok.json`. It contains only the 64 frozen cell bindings and six validated native scores per cell, plus the current executor hash and a self-commitment; it deliberately omits raw prompts, stories, payload bytes, native requests, and responses. `--replay-projection` reconstructs that exact file from the replayed collector without provider contact. The final analyzer consumes this file with the independently produced Sol projection in a closed two-file root.
