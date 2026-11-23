# Saved census continuation sources

These programs continue the saved census with explicit metadata memberships and
dispositions. They support local regeneration when the exact private inputs and
digest-bound recipes are available. Public source alone cannot reproduce the
completed census: recipes, raw inputs, private ledgers and generated exports are
kept local. The source itself includes aggregate contract constants and artifact
hashes.

| Program | Required saved evidence | Scope |
| --- | --- | --- |
| `regenerate_v3.py` | Complete regeneration v2, registry **v6**, TTCW snapshots 051/052 | Rebuild nine count/disposition exports; see [README-v3.md](README-v3.md). Its registry-v6 snapshot has 57 unresolved declarations. |
| `census_train_v14_metadata.py` | Private V14 TRAIN schedules and receipt metadata | Project metadata through the pinned public lexical reader. |
| `registry_v7.py` | Registry v6 proof bundle and saved V14 metadata census | Add the qualified metadata membership; 56 declarations remain unresolved. |
| `census_train_v13_metadata.py` | Private V13 TRAIN metadata and exact V14 helper source | Project V13 metadata without opening score/target values. |
| `registry_v8.py` | Registry v7 proof bundle and saved V13 metadata census | Add the V13 membership; 55 declarations remain unresolved. |
| `census_v14_pilot_metadata.py` | Private V14 pilot metadata and exact V14 helper source | Keep preparation records separate from historical receipt metadata. |
| `registry_v9.py` | Registry v8 proof bundle and saved pilot metadata census | Add the pilot membership; 54 declarations remain unresolved. |

Registry v9 is a later, separate continuation. It does not make regeneration v3
use registry v9 automatically. The v9 contract covers 76 declaration packages,
115 overlapping coverage edges and 12 census namespaces, including nine
metadata-qualified packages. These counts cannot be summed into independent
judgments or provider contacts. Preparation metadata does not establish a vote
or permission to retry.

The metadata readers depend on the exact public source
`../hbq-matched-hanna-20261004/prepare.py` (SHA-256
`2d82e4959c3296ccaa6e6521adb46f85588427d429a544b36a2891ebaea8c7b0`).
V13 and pilot readers also pin their sibling V14 helper. Registry continuations
verify prior report, receipt, recipe, implementation and private-ledger bundles.
Keep earlier implementations: they remain hash-bound historical dependencies.

Each script exposes its arguments with `python -B <script> --help`. Execution
requires the recipe's exact digest and fresh owned output paths under the
specified control root. `--dry-run`, where offered, still reads and verifies
private inputs; it is not a source-only check. Syntax and help checks establish
source integrity and entrypoint availability, not replay of a saved census.

This remains a partial artifact/request/leaf census. Metadata membership does
not establish native admission, current tools-disabled collection, physical
contact totals, human validity or completion of the research and release Goal.
The unresolved declarations require their own exact evidence reconciliation.
