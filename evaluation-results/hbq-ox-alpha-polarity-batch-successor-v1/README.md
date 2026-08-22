# Ox polarity and batch successor

Frozen 3-story, 4-leaf diagnostic screen. It compares positive and reviewed
failure wording at batch sizes 1 and 4: 30 calls per screen, plus an optional
balanced confirmation screen. The package contains no story text and no
production recommendation.

`study.py` remains offline. `run_live.py` is the separate private execution
boundary: it stages positive and reviewed-failure registry projections, freezes
the 30-call schedule, runtime, disclosure, and fresh zero-cost bindings, then
uses the existing cap-one hardened Nous runner. It creates an immutable intent
before each logical request and a result after it; a request with no result is
not resent. Only a sealed, outbound-only HTTP 524 with no result-bearing
artifact is eligible for a later retry. Eligibility replays the v9 signed Judge
boundary, HMAC-evidenced Judge/ProveLock topology, request/payload bindings,
serialization proof, receipt, and provider identities. Accepted batches also
replay the raw cap-one request, checkpoint/schema, prompt, receipt, and
identities. Non-524 failures, malformed evidence, inbound 524s, charge
signals, and HTTP 402 are terminal quarantine/global-stop outcomes. A
create-exclusive execution claim spans pre-contact through a sealed result; a
leftover claim or intent is fail-closed. Counterpart wordings are never in the
same physical batch.

The first screen is 30 logical calls with at most 150 physical sends (five
eligible-524 attempts per logical call). The optional confirmation has the same
30/150 ceiling. A charge/402 stop seals a stopped settlement that explicitly
counts the unsent calls; five eligible 524s for one call are terminally
exhausted rather than silently retried again.

The work root is private and external to this repository because it contains
the selected source inputs and projections. The tracked package carries no
story prose or absolute paths. Preparation, execution, and settlement are
deliberate separate commands:

```powershell
.venv\Scripts\python.exe evaluation-results\hbq-ox-alpha-polarity-batch-successor-v1\run_live.py --prepare --v9-work-dir <private-v9-root> --zero-cost-proof <fresh-proof> --work-dir <new-private-root>
.venv\Scripts\python.exe evaluation-results\hbq-ox-alpha-polarity-batch-successor-v1\run_live.py --work-dir <private-root>
.venv\Scripts\python.exe evaluation-results\hbq-ox-alpha-polarity-batch-successor-v1\run_live.py --progress --work-dir <private-root>
.venv\Scripts\python.exe evaluation-results\hbq-ox-alpha-polarity-batch-successor-v1\run_live.py --settle --work-dir <private-root>
```

`--progress` is a non-final snapshot. `--settle` refuses to write a settlement
until every call is terminal or an explicit global stop has ended the screen.
