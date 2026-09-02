# Fresh96 future-confirmation Grok reconciliation

This provider-free package reconstructs a collector from the immutable V10
Fresh96 future-confirmation Grok `r1` execution root and its matching frozen
schedule. It never retries, resends, or contacts a provider.

The runner left each native envelope as pretty JSON. Reconciliation preserves
those raw bytes and accepts that formatting. It also accepts legitimate
evidence text containing the plural word “Placeholders”; only an exact
placeholder sentinel is rejected. Workspace-search/tool-use placeholder
patterns remain rejected.

The reconciled collector has 64 cells, zero provider calls and zero process
launches during reconciliation, and 64 historical process launches. Native
endpoint contact cardinality remains unproven. It is measurement-only:
there is no Sol result, selection, promotion, runtime, or endpoint-pooling
authority.

After reviewing this package, write a collector only to a fresh external
path, then replay it against the same immutable execution and freeze roots:

```text
python reconcile.py --output-root <immutable-r1-root> --freeze-root <immutable-freeze-root> --collector-path <existing-collector>
```

The command-line surface replays an existing collector. Use the Python
`write_collector` function only when supplying a fresh external output path.
