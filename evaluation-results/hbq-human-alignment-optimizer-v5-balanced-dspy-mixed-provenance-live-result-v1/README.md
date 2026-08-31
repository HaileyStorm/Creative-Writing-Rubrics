# HANNA v5 Grok descriptive result

This is the immutable public result publication for the completed v5
Grok-primary development leg. It commits the collector, schedule, alias
manifest, executor, and source-result hashes while retaining the original
result's internal commitment. `result.json` separately records publication
geometry and repeats every source-artifact pin; neither field alters the
committed source-result projection.

The frozen schedule contained 33 logical rows. Three are byte-identical
baseline descendants retained only for lineage, leaving 30 unique outbound
payloads and ten effective candidates. Each effective candidate has one
receipt-backed observation in each of three prompt groups. All recorded Grok
requests had tools disabled.

The baseline `candidate-102cc7f06c9a99a7` has equal-group MAE
`1.1296296296296295`. The lowest observed candidate,
`candidate-69720ac6257db007`, has `0.6666666666666666`: a descriptive delta
of `-0.4629629629629629` (a `40.98360655737705%` relative reduction). Its
three group deltas from baseline are `-0.2222222222222222`,
`-0.6666666666666665`, and `-0.5`.

This is **Grok-only descriptive development evidence**. A local Grok CLI
lifecycle and saved envelope do not prove native endpoint contact cardinality;
that cardinality remains `unproven`, so the strict v5 projector rejects these
receipts. The package does not select a winner or establish strict-v5
projection, Sol validation, confirmation, general HANNA gain, promotion, or
runtime authority.

Run `python verify.py` to recheck the local publication's commitments and
equal-group geometry without making provider calls.
