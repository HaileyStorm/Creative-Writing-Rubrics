# Public desc17 withdrawal relationship

The published desc17 input-fidelity audit withdraws the earlier desc17 semantic
and generalization conclusions. This census supplement makes that relationship
explicit so the original result is not mistaken for usable semantic evidence.

`link.py` binds the four public audit files, the original public result and its
publication manifest by SHA-256. It invokes only the existing public package
validator and verifies the original result identity. It does not invoke the
private collector audit or independently reproduce the reported fidelity defect.
The historical commit cited by the audit is not independently checked here.

From the repository root:

```powershell
.venv\Scripts\python.exe -B evaluation-results\hbq-census-desc17-withdrawal-link-v1\link.py --verify
.venv\Scripts\python.exe -B evaluation-results\hbq-census-desc17-withdrawal-link-v1\link.py --self-test
```

Without arguments the script writes the deterministic aggregate to standard
output. `--verify` compares it to the saved aggregate; `--self-test` checks that
altered public source bytes are rejected, using an in-memory mutation.

This supplement does not modify the historical registry or resolve its private
locators. The reference count remains 54 unresolved declarations and is not
recomputed here. These public relationships add no native/request/leaf
admissions, observations or provider contacts. Runtime and promotion authority
remain absent, and the full census and research Goal remain incomplete.
