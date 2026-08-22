# Batch-curve V3 offline analysis v1

This argument-driven publication step verifies frozen execution data against
Git commit `943282b`, then emits only sanitized aggregate results and commitments.

It does not call a provider or recommend a production batch size. Private
evidence is an input to validation and is never copied to output.

```powershell
python analyze.py --repo-root <clean-repository> --execution-public-root <public-evidence> --execution-private-root <private-evidence> --repaired-settlement-root <repaired-v2> --output-dir <fresh-output>
```
