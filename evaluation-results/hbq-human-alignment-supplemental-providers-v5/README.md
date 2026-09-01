# Supplemental HANNA Nous v5

v5 is the executable successor to the provider-free v4 compatibility snapshot. It prepares three fresh, sequential batch-8 cells: the exact first eight question IDs from each of v4's three historical batch-16 lineages. Preparation records current runner, launcher, and hardened bridge hashes; immutable source, prompt, and task-contract fingerprints; a tool-free disclosure and authorized acknowledgement; and a current zero-new-spend, existing-credit-only, no-paid-fallback route proof. It makes no provider contact.

The current runner uses a separate `native-run/` directory and invokes the callback only after creating `run.json`, `response.schema.json`, and exactly `responses/batch-0001.prompt.txt.gz`. v5 freezes a reviewed per-cell scope compatibility override with its preparation, accepts precisely those runner-owned precontact artifacts, binds the gzip prompt and schema bytes to the callback context, revalidates every preparation commitment and the route beside the callback, then writes the sole launch intent. A return or error after intent is terminal reconciliation; the same root never resends. Successful cells must contain one sealed, tool-free native Nous result with exactly one physical HTTP attempt, zero recovered requests, a distinct validated bridge session, and duration below 100 seconds. They remain `PROVISIONAL_BREADTH_ONLY`: this route supplements rather than replaces Sol and does not establish an exact reasoning gate.

Prepare only after producing a fresh reviewed route proof:

```powershell
$env:PYTHONPATH='src'
python evaluation-results\hbq-human-alignment-supplemental-providers-v5\prepare.py --v4-work-dir <fresh-v4-root> --route-proof <current-route-proof.json> --work-dir <fresh-v5-root>
```

Execute only after inspecting that provider-free root:

```powershell
$env:PYTHONPATH='src'
python evaluation-results\hbq-human-alignment-supplemental-providers-v5\executor.py --work-dir <fresh-v5-root> --allow-remote
```
