# Retained semantic and long-form diagnostics

27 October 2026

The retained results support descriptive findings about coverage, score concentration,
agreement and repeatability. They do not establish human alignment or a successful
rubric candidate. This synthesis copies existing aggregates and adds no judgments,
native replay, semantic validation, scoring or provider calls. The experiments remain
separate; their observations are not pooled into a new quality estimate.

## Semantic and cross-form campaign (P1b)

The frozen design contains eight AI-generated families and 24 variants: 12 short
narratives, six bounded two-scene work segments and six complete free-verse poems.
It planned 1,584 requests across Sol and Grok, including three cycles and selected
bank/pair sentinels. Its retained analysis records 990 accepted requests, 15 semantic
rejections, one ambiguous attempt, one unadmitted attempt and 577 then-untouched
requests. These are historical dispositions, not a fresh census or permission to retry.

Initial Sol HBQ scores concentrate near the top of their native 0–100 scale:

| Form | Complete scalar profiles / planned | Mean | Range | Scores at least 95 |
|---|---:|---:|---:|---:|
| Short narrative | 10 / 12 | 95.9357 | 84.0198–98 | 8 / 10 |
| Bounded work segment | 6 / 6 | 93.5198 | 86.793–98 | 3 / 6 |
| Free-verse poem | 6 / 6 | 91.6244 | 79.612–98 | 2 / 6 |

There are no exact HBQ ceiling scores in these rows. Comparator means use different
native scales and, for narratives, different observed denominators; they are not a
shared-denominator leaderboard. Compact poem scores are all 4/5. High scores and low
variation can motivate a discrimination question but cannot identify the correct
method without a suitable reference. The aggregate retains each arm's original near-
extreme increment: HBQ uses five points and compact uses one native point. These are
not newly imposed common percentage cutoffs.

Same-text direction agreement is mixed. Initial Sol HBQ agrees with holistic on 4/6
observed narrative pairs, 2/4 segment pairs and 3/4 poem pairs; with compact on 4/6,
1/4 and 1/4; and with bidirectional pairwise on 3/6, 3/4 and 2/4. Six of eight planned
narrative pair comparisons are observed. These compare methods, not agreement with
correct defect labels. Grok HBQ scalar coverage is only 2/12 narratives, 0/6 segments
and 1/6 poems; only one narrative and one poem scalar are shared with Sol.

Initial Sol pairwise orientations are consistent for 8/8 narrative, 4/4 segment and
4/4 poem pairs. Complete three-cycle HBQ scalars exist for one of two Sol narrative
sentinels, one segment and one poem. The segment's absolute differences across cycles
0–1, 0–2 and 1–2 are 0.5352, 0 and 0.5352 points; the poem's are 5.44, 3.52 and 1.92.
These sparse sentinels do not establish population reliability. The machine-readable
aggregate retains planned/observed denominators, missingness and agreement caveats.

The later [AI intent review](../hbq-semantic-crossform-p1b-intent-v1/review-summary-002.json)
admits one narrow ordinary-physical-state consequence triad; seven full triads remain
unadmitted, with 25 unresolved disagreements. It is retrospective AI review across
eight packets and seven conversations, supplies no human votes and does not provide
independent endpoint evidence. The original campaign's `oracle_accepted=false` stays
unchanged. Its results cannot become a defect-detection accuracy test retroactively.

The installed wording/scope repairs documented in the
[repair journey](../../docs/VALIDATION_AND_REPAIR_JOURNEY.md) are a separate lineage.
These historical results do not automatically measure the current wording. Completed
negative architecture and discordance studies also retain their stated scope; none
of these aggregates promotes a candidate.

## Long-form dependency and grounding evidence

The older dependency pilot concerns two familiar human-authored novellas. Its retained
111 admitted logical observations comprise 57 strict admissions and 54 exploratory
CRLF/span descendants. Those descendants are not 54 new model judgments. The pilot
planned 464 judging requests, with source-summary generation counted separately.

| Retained condition | Observed result | Meaning |
|---|---|---|
| HBQ whole-work banks in the pilot | Zero complete scores across eight planned bank profiles | Incomplete banks supply no whole-work HBQ ranking |
| Whole-work comparator profiles | Four assessed of 24 planned; compact 5/5 and holistic 7/7 on each of pg209/pg43, Sol cycle 0 | Two works, with all four native ratings at their ceilings |
| Later pg43 bank, original strict admission | 10 accepted and 18 rejected of 28 packets | No complete bank or score |
| Same later bank, opt-in derived grounding | 27/28 eligible; packet 23 still ineligible; score null; scorer never called | Improved grounding eligibility on the same returns, without a quality-gain claim |

“Zero whole-work scalars” would be too broad: the result is zero complete **HBQ**
scores alongside four assessed comparator profiles. There is still no matched HBQ
whole-work scalar comparison. The later pg43 bank is a separate condition and is not
pooled with the legacy pilot. It reused ten cached native proofs, verified the 18
original rejected returns and performed 28 derived semantic checks; this synthesis
does not repeat those operations. Packet 23's case mismatch remains outside
whitespace-only grounding. No partial bank is spliced or scored.

AI summaries, maps and interpretations remain diagnostic aids. Familiarity and prior
case knowledge are possible. Submitted-byte receipts do not prove that a model read
an entire work or avoided truncation. These sources establish no human-alignment
gain, unseen-novel or population generalization, fixed-form verse validation,
performed script/audio result or nonfiction result. Scales and grounding policies
remain separate, and the canonical baseline remains unpromoted.

## Provenance and reproduction

`aggregate.json` copies the retained scalar, agreement, repeat and missingness fields.
Its input and source commitments preserve the original analysis boundaries. Raw
texts, responses, judgments, labels and operational account details are excluded.
The historical native envelopes were not fully reconstructed, and physical-contact
cardinality was not proven; retained qualification flags are not upgraded here.
The full research program remains incomplete.

`regenerate.py` reproduces this projection from the exact reviewed aggregate inputs:

```text
python -B regenerate.py --p1b <P1b-evidence-matrix.json> --p1b-sources <P1b-sources.json> --longform <longform-aggregate.json> --output <new-output.json>
```

The named input aggregates remain private and are hash-bound in the script; this
package does not distribute their underlying research records. Regeneration copies
existing measurements and removes local paths. It does not reconstruct raw evidence
or prove native acceptance anew. Existing rejections and unresolved attempts stay
missing, and no candidate or scoring default changes.
