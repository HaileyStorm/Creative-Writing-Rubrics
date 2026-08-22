# Preface-pilot cell-17 repair chain v2

This is a separate, hash-bound descendant of the original preface pilot and
its continuation. The original cell-17 failure remains in the primary
analysis. The already accepted first quote-only repair remains immutable. This
package can send at most three further quote-only repairs, each for the next
canonical failure in the combined cell. A repair keeps the original leaf's
verdict and confidence locked, is part of the same logical sample, and never
adds a vote.

`prepare`, `render_next_disclosure`, and `settle_offline` make no provider
calls. Every remote step requires `--allow-remote` after its disclosure has
been reviewed. The executor never resends a leaf already accepted as valid.
It stops when the full combined cell validates, or seals the sensitivity route
unavailable after a non-quote failure, uncertain contact, or the bounded cap.

```powershell
$exe = '.\.venv\Scripts\python.exe'
$work = 'C:\path\to\fresh-repair-chain-public-root'
$private = 'C:\path\to\fresh-repair-chain-private-root'
$originalWork = 'C:\path\to\original-public-root'
$originalPrivate = 'C:\path\to\original-private-root'
$continuationWork = 'C:\path\to\sealed-continuation-public-root'
$continuationPrivate = 'C:\path\to\sealed-continuation-private-root'

& $exe evaluation-results/hbq-ai-writer-preface-v1-repair-chain-v2/executor.py $work $private $originalWork $originalPrivate $continuationWork $continuationPrivate --prepare
& $exe evaluation-results/hbq-ai-writer-preface-v1-repair-chain-v2/executor.py $work $private $originalWork $originalPrivate $continuationWork $continuationPrivate --render-next-disclosure
# Only after reviewing that exact disclosure:
& $exe evaluation-results/hbq-ai-writer-preface-v1-repair-chain-v2/executor.py $work $private $originalWork $originalPrivate $continuationWork $continuationPrivate --execute-one --allow-remote
& $exe evaluation-results/hbq-ai-writer-preface-v1-repair-chain-v2/executor.py $work $private $originalWork $originalPrivate $continuationWork $continuationPrivate --settle-offline
```

Use the dedicated tests. The sealed-evidence checks are opt-in through the
four `CWR_PREFACE_*_ROOT` environment variables named in the test file.
