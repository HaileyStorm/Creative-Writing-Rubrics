# Desc18 Fresh96 open replication optimizer

This provider-free analyzer reconstructs the committed public/open Fresh96 schedule, replays all 64 immutable native receipts, and compares retained descendant13 with retained child20 by prompt-group-equal MAE over 16 groups.

It uses Optuna's frozen six-setting `GridSampler` and DSPy examples only to record development evidence. It makes zero model, LM, or `Predict` calls. Child20 can reach a Sol veto only by strictly improving raw MAE and being no worse under every frozen setting; Sol cannot select a substitute.

The analyzer is bound to the reviewed executor, contract, README, and regression test at commit `4d3b2ef20f5fad4ea0974e888f37550d4b8480f2`.

```powershell
python evaluation-results/hbq-human-alignment-optimizer-v9-desc18-broad-replication-development-optimizer-v1/analyzer.py --freeze-root C:\path\to\desc18-freeze --collector-path C:\path\to\collector.json
```
