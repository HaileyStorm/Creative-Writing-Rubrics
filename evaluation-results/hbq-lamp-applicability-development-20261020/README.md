# Retained LAMP passage applicability

20 October 2026. A retrospective coverage diagnostic from **38 complete initial Sol HBQ banks**, comprising **6,460 saved leaf decisions**. This identifies where the saved judge used applicability and assessability states. It does not establish whether those judgments were correct or whether a rubric change would improve human agreement.

## Results

| Saved state | Leaf decisions |
|---|---:|
| YES | 4,026 |
| NO | 1,233 |
| NOT_APPLICABLE | 1,135 |
| CANNOT_ASSESS | 66 |
| Total | 6,460 |

All 38 banks contain the complete 170-leaf membership, with zero missing native leaves. Of the 5,325 applicable cells, 5,259 are binary assessed and 66 are CANNOT_ASSESS. A complete response is therefore distinct from a fully assessed response. These are unweighted cell counts. The saved canonical weighted coverage ranges from 0.9561 to 1.0000, with a mean of 0.9868895; it was not recomputed.

CANNOT_ASSESS occurs in 32 of 38 banks and in 18 of 170 criteria. The most frequent cases are:

| Criterion | YES | NO | NA | CA |
|---|---:|---:|---:|---:|
| Authorization for invention or alteration (`core.task_and_brief_fidelity.intervention`) | 27 | 1 | 0 | 10 |
| Character consistency with supplied sheets or prior behavior (`craft.narrative.characterization.canon`) | 0 | 0 | 28 | 10 |
| Excerpt or partial-draft status supplied to the judge (`penalty.unflagged_incomplete.status`) | 30 | 0 | 0 | 8 |
| Consequential character choices (`craft.narrative.characterization.agency`) | 24 | 3 | 5 | 6 |

Nine criteria are NOT_APPLICABLE in all 38 banks:

- `core.economy_and_relevance.digression`
- `core.length_and_scope_fit.explicit`
- `core.task_and_brief_fidelity.exclusions`
- `core.task_and_brief_fidelity.length_hard`
- `core.task_and_brief_fidelity.tense`
- `core.voice_and_stylistic_identity.project_fidelity`
- `form.prose.general_prose_fiction.completion`
- `penalty.repetition.long_range`
- `penalty.unflagged_incomplete.unit`

Thirteen criteria receive no binary judgment across these banks. Besides those nine, they are source fidelity, characterization canon, dialogue voice distinction and scene context fit. Their full distributions, question wording and module totals are in `results.json` and `criteria.csv`.

## Why scope matters

The frozen contract declares `artifact_kind: prose_fiction`, `declared_scope: passage`, `completion_status: unknown`, and `contract_id: lamp_passage_quality_v1`, version 1. It directs the judge to assess the visible local purpose without requiring unseen setup, whole-work closure or a complete character arc. Visible local defects remain assessable.

Audience, preferences, priorities, weighted goals and binding requirements are empty. No dynamic leaves or invented requirements are added. The shared task-context constraint is: “Assess the visible passage; unseen whole-work closure is not required.”

Persistent inapplicability can correctly reflect that contract. Absent supplied character sheets or neighboring scenes can also explain unassessability. These counts do not justify deleting criteria or treating NA as NO. Conversely, unknown completion status should not hide a visible local defect.

### Status-disclosure follow-up

A subsequent saved-context review selected the two lexicographically lowest private paragraph IDs in each of the YES and CANNOT_ASSESS groups for `penalty.unflagged_incomplete.status`. All four frozen outbound prompts contained the shared writing instruction and the metadata declaring passage scope and unknown completion. This selected sample establishes no rendering omission.

The criterion asks whether excerpt, fragment, sample, partial-draft or unfinished status is supplied to the judge. The two CANNOT_ASSESS notes treat actual excerpt or unfinished status as unresolved despite disclosed passage scope. The two YES notes treat passage scope and explicit uncertainty as sufficient disclosure. The wording does not resolve those interpretations: evaluation scope does not establish the underlying work's completion status, while explicit uncertainty still communicates an evaluation limit.

The useful unscored diagnostic is: **Passage scope and unknown whole-work completion were supplied; the criterion does not specify whether explicit uncertainty satisfies its disclosure requirement. Preserve the original verdict.** No replacement question or score change is validated by these four cases. Their different passages and writing instructions also prevent treating them as identical-input repeats. Model notes are explanations, not verified causal accounts; independent agent review is not human validation.

The retained private review packet has SHA-256 `b013e44225a3e0f3b4de19c35f0000c4e583bcb86fe92e2274a9071a61369e14` (23,470 bytes). It binds original context, contracts, response notes and bounded frozen-prompt slices. Source prose, private identities and response excerpts are excluded here. No provider contact, scorer call or human-target read occurred in this diagnostic. Frozen outbound bytes do not establish backend or wire attestation. The selection supports this narrow ambiguity diagnosis, not a defect rate or a claim that either verdict is wrong.

Authorization and digression remain separate follow-ups requiring their actual context and relevant passages. Any prompt change would define a separate future condition. The canonical rubric and existing predictions remain unchanged.

## Selection and limitations

This selects every `sol / hbq / SCORED` bank in the retained 032 profile file. All have repeat index 0 and exactly the frozen 170-question membership. The parent analysis has 280 incomplete HBQ banks, including planned repeats; those banks are excluded here. The 38 paragraphs are availability-selected and share source triplets, so they are not 38 independent representative samples.

The saved historical tool controls remain unqualified. Keep these results separate from the contemporary tools-disabled Sol comparison. There is no new provider contact, scorer execution, semantic or native replay, repeatability estimate, confidence interval, human-target decoding, human correctness claim or candidate promotion. The source's human references are historically development-exposed; this computation does not read them. Independent agent review of scope metadata is not human validation.

## Reproduction and provenance

Run the real command against the retained private source files and a **new** output directory:

```text
python analysis.py --profiles PATH_TO_PRIVATE_BANK_PROFILES --compiled PATH_TO_FROZEN_COMPILED_JSON --output NEW_DIRECTORY
```

`analysis.py` pins both input hashes, selects the 38 banks, checks full question membership, counts the four states and writes aggregate JSON and CSV. It does not import the scorer or contact a provider. The single recorded execution completed successfully; its output is published here. Inputs are not bundled, so independent reconstruction requires authorized access to the retained sources.

Source commitments:

| Source | SHA-256 |
|---|---|
| Retained 032 private bank profiles | `aa6a9e809f53e6640497e7fa3d5efe6f583426b794a90f031832562cb7354a69` |
| Frozen compiled short-form rubric | `fdb8d9f49bdc9183db0783c461f2e58d044fd088a7e3cfaea7bb95af501e93a4` |
| Parent saved-prefix report | `f7e9601fd69ba0d2df534e4cef904599661abf37eb5c73cafb0f4c2dae10ad5e` |
| Frozen LAMP manifest | `480aa86df271078e322ac85cf8cfe5fe6ed02344138e218900cfe03c069b6ab6` |
| Shared task-context projection | `d170185d29ec94ecab2e621e3f3afec5e7178afa6847e4be22d9ef71934f330a` |

LAMP source provenance follows [Salesforce creativity_eval](https://github.com/salesforce/creativity_eval/tree/3d029879df6878f611363db88cc02d465699bc51). Underlying passage and human-reference restrictions remain in force. This package contains rubric wording and aggregate model-state counts; it excludes source prose, human labels, assessor identifiers, private paragraph identities and operational account details.
