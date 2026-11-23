# HANNA Sol validation: historical source-byte link

This provider-free check links the public [seven-group Sol development
result](../hbq-human-alignment-optimizer-v5-f20-broader-development-sol-result-v1/README.md)
to four files in its declared historical source commit. Their Git-object bytes
match the SHA-256 values in the public result verifier: the executor, its study
contract and README, and its test file. The result and its publication contract
also agree on the source commit and executor hash.

To reproduce from a clone containing the specified commits:

```sh
python evaluation-results/hbq-hanna-v5-sol-source-link-v1/verify.py --repo .
```

The check reads committed public files with `git show`. It does not execute
the historical executor, open the human-reference table or local run receipts,
or contact a model provider. It does not establish that the source actually
executed in the 21 reported process lifecycles, verify their native or account
provenance, count physical provider contacts, or establish independent votes.
The seven-group result remains descriptive development evidence, with no
confirmation, selection, promotion or runtime authority.
