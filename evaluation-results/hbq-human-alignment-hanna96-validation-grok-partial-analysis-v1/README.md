# Fresh96 Grok partial analysis

This is a provider-free analysis of one closed 64-cell Grok Fresh96 root. It accepts exactly 63 receipt-backed cells and one known terminally ambiguous descendant cell. The ambiguous cell is preserved but excluded; no score is imputed and no resend occurs.

`analyze.py` validates the pinned Fresh96 freeze and Grok wrapper, then replays the wrapper's own admission path for every successful cell. That binds the scheduled payload, runner prompt artifact, native request, native response/envelope, receipt, settings, and identity as one chain. It writes a fresh canonical result specified by `--result-output`; it never edits the source root.

The public result contains only aggregate coverage and endpoint-specific MAE: 31 paired items across 16 groups, plus the 15 fully complete groups / 30-item sensitivity. It deliberately omits source story text, prompt IDs, item IDs, native identities, and filesystem paths. It makes no pooling, imputation, candidate-selection, confirmation, generalization, promotion, or runtime claim.

Example:

```powershell
python evaluation-results/hbq-human-alignment-hanna96-validation-grok-partial-analysis-v1/analyze.py --source-root C:\path\to\closed-root --result-output C:\path\to\fresh-result.json
```
