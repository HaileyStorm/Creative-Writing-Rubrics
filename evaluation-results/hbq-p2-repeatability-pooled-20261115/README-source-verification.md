# Checking published aggregates against retained records

`reproduce-from-records.py` is a read-only source-level check for the three
published P2 aggregate files in this directory. It requires four private
inputs: the retained request/leaf index, frozen manifest, stopped snapshot,
and the original owner root containing the accepted record paths. Supply them
with `--index`, `--manifest`, `--snapshot`, and `--owner-root`, respectively.
The index, manifest and snapshot are digest-pinned in the script. The saved
record paths are absolute; this version requires their original layout and
does not claim cross-host portability.

The check verifies the manifest's 100 artifact commitments, the 213 accepted
terminal bindings and their saved attempt, admission, native-result and
response file digests, and the request/leaf identities in the private index.
It reconstructs observed HBQ and TTCW-adaptation cycle comparisons, kappa,
the stated missing-state bounds and comparator score summaries, then compares
them to the three pinned published aggregate files. It also verifies that the
two arms reference the same frozen source files for the three stories.

Only metadata for the three held requests is read from the pinned index; held
terminal and response files are not opened. Accepted responses and frozen
artifacts, including private prose, prompts and possible quotations, are read
in memory but are not printed or written. The summary output contains only
aggregate counts. No provider call or human-target read is made.

This verifies retained bytes and the stated aggregate arithmetic. It checks
saved admission decisions rather than re-adjudicating their semantics, and it
does not establish provider identity, physical-contact cardinality, billing
settlement, deployed prompt bytes, human alignment or a complete historical
census. Matching source files do not prove that the two instruments had
identical surrounding instructions. The three held requests remain untouched.
