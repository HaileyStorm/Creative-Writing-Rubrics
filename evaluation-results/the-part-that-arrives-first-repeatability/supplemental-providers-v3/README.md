# Supplemental provider study v3

This sealed protocol tests the published story against the immutable `established-v4` contract: the same 178 HBQ leaves, strict native schemas, batch-32 schedule, checkpoint-4 response artifacts, and retry/normalization policy. GPT-5.6 is the primary study and is neither rerun nor altered here.

Grok 4.6/high and Nous DeepSeek V4 Flash/max each receive five fresh serial repetitions. They are provider conditions, not rubric arms. Each condition has its own append-only planned/completed journal, manifest commitments, and provider-receipt proof. The report exposes paired HBQ differences and each native method's within-scale repeatability; it never averages or ranks incompatible scales.

Both providers presently require `allow_unattested_reasoning`; results are explicitly provisional on that point. Nous Flash promotion to Pro-0813 is predeclared in the contract and may occur only after the frozen HANNA development threshold—not because of this story's results.

The conditional Pro route requires a hash-bound `promotion-decision.json` tied to the exact HANNA-v3 contract/analyzer, GPT baseline summary, and frozen Flash macro threshold.

Run externally, after reviewing the remote disclosure:

```powershell
python run_study.py --work-dir C:\path\to\external-work --provider grok_4_6_high
python run_study.py --work-dir C:\path\to\external-work --provider nous_flash_max
python analyze_study.py --work-dir C:\path\to\external-work --output-dir C:\path\to\published-analysis
```
