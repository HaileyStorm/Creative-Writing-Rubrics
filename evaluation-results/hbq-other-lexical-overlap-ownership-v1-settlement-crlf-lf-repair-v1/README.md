# L2 CRLF/LF settlement repair v1

This package is a settlement-only successor for the completed L2 lexical
ownership execution. It reads the frozen execution package and its private
evidence without modifying either. It makes no provider calls and exposes no
execution path.

The sole compatibility rule permits an observed rendered prompt whose bytes
become the frozen canonical UTF-8/LF prompt after replacing only `CRLF` with
`LF`. A lone carriage return or any other byte difference fails settlement.
Both raw and canonical SHA-256 commitments are retained for every execution
slot. All 216 execution slots, 72 three-repeat cells, image receipts, route
reports, response schema, typed evidence, exact textual quotes, identities,
and repeat histories remain required.

Run settlement against the immutable execution root and a distinct, empty
settlement root:

```powershell
python run.py settle --execution-root <private-execution-root> --settlement-root <private-settlement-root>
```

An integrity-verified public aggregate is intentionally diagnostic-only:
`DIAGNOSTIC_FAIL` and `promotion: none` regardless of metrics. Any integrity
failure is `INCOMPLETE` and non-publicable. Neither outcome alters a rubric,
prompt, ownership assignment, split, or weight.
