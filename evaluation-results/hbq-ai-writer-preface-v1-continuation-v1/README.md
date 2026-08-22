# Preface-pilot continuation v1

This separately frozen descendant continues only original sequences 18–24.
The original public/private roots are read-only, hash-bound evidence. Cell 17
remains a terminal failure in the primary analysis. A narrowly scoped repair
may supply a separate sensitivity result, never an independent repeat or a
replacement for the failure.

Each suffix cell receives a fresh, unscored capacity preflight followed by at
most one scored `codex` / `gpt-5.6-sol` / `high` call. A later structural
failure seals that cell and advances to the next scheduled cell; it is not
retried. The only repair target is the failed leaf in cell 17, with the
original verdict and confidence locked into the repair request. Quote-only
repair comes first; one separately labelled full single-leaf regrade is
permitted only if quote repair is invalid.

`prepare`, `render_next_disclosure`, and `settle_offline` make no provider
calls. All remote operations require `--allow-remote` after the disclosure is
reviewed. New public and private roots must be fresh and disjoint from one
another and from the original roots.

```powershell
.\.venv\Scripts\python.exe -m pytest --basetemp .pytest-ai-writer-preface-continuation-v1 tests/test_ai_writer_preface_continuation_v1.py
.\.venv\Scripts\python.exe -m py_compile evaluation-results/hbq-ai-writer-preface-v1-continuation-v1/executor.py
```

The original roots remain read-only. Prepare new, empty continuation roots,
then render each disclosure before authorizing its matching remote step:

```powershell
$exe = '.\.venv\Scripts\python.exe'
$work = 'C:\path\to\new-public-continuation-root'
$private = 'C:\path\to\new-private-continuation-root'
$originalWork = 'C:\path\to\original-public-root'
$originalPrivate = 'C:\path\to\original-private-root'
& $exe evaluation-results/hbq-ai-writer-preface-v1-continuation-v1/executor.py $work $private $originalWork $originalPrivate --prepare
& $exe evaluation-results/hbq-ai-writer-preface-v1-continuation-v1/executor.py $work $private $originalWork $originalPrivate --render-next-disclosure
& $exe evaluation-results/hbq-ai-writer-preface-v1-continuation-v1/executor.py $work $private $originalWork $originalPrivate --capacity-preflight --allow-remote
& $exe evaluation-results/hbq-ai-writer-preface-v1-continuation-v1/executor.py $work $private $originalWork $originalPrivate --execute-one --allow-remote
```

Repeat the disclosure/preflight/execute sequence until all suffix cells are
terminal, then use `--settle-offline`. Cell 17 repair is optional and must be
reviewed separately with `--render-repair-disclosure`; run `--repair-cell17
--allow-remote` first without `--full-regrade`. A full fallback is permitted
only after an invalid quote repair and is a fresh single-leaf regrade: it does
not send the original locked verdict or confidence.

```powershell
& $exe evaluation-results/hbq-ai-writer-preface-v1-continuation-v1/executor.py $work $private $originalWork $originalPrivate --render-repair-disclosure
& $exe evaluation-results/hbq-ai-writer-preface-v1-continuation-v1/executor.py $work $private $originalWork $originalPrivate --repair-cell17 --allow-remote
# Run the following fallback only if the quote-only repair sealed invalid:
& $exe evaluation-results/hbq-ai-writer-preface-v1-continuation-v1/executor.py $work $private $originalWork $originalPrivate --render-repair-disclosure --full-regrade
& $exe evaluation-results/hbq-ai-writer-preface-v1-continuation-v1/executor.py $work $private $originalWork $originalPrivate --repair-cell17 --full-regrade --allow-remote
```

The sealed-evidence integration tests are opt-in and use untracked paths:

```powershell
$env:CWR_PREFACE_LIVE_PUBLIC_ROOT = 'C:\path\to\original-public-root'
$env:CWR_PREFACE_LIVE_PRIVATE_ROOT = 'C:\path\to\original-private-root'
.\.venv\Scripts\python.exe -m pytest tests/test_ai_writer_preface_continuation_v1.py
```
