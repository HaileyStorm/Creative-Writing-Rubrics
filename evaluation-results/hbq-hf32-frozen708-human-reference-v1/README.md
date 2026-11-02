# HF32 frozen-candidate human-reference pilot

This closed descriptive pilot evaluates the previously frozen candidate 708 on
32 retained human-referenced works. It does not support candidate promotion or a
general winner claim. The candidate changed no verdicts in the 27 complete HBQ
banks, so its reported scores equal the historical projection of those same banks.

The aggregate was prepared on 2026-11-02. [aggregate.json](aggregate.json) contains
the recorded metrics, denominators, attrition, conditional sensitivity and
hash/byte commitments. Its SHA-256 is
`ac187d94306f8179173915857d06d54f8a1ceca74c3008e19eaca02bbfdb914e`
(22,662 bytes).

## Matched comparison

All three arms have 19 paired works on each human-reference axis in their common
input view. There are 21 works with scores available in all arms; target
availability reduces each paired comparison to 19. The paired comparison is
missing 13 of the fixed 32 works. These are work counts, not independent judge,
request or human-subject counts.

| Projection | Expert creativity mean-of-two, Spearman rho (n=19) | Nonexpert creativity median, Spearman rho (n=19) |
| --- | ---: | ---: |
| Historical HBQ | 0.293140 | 0.390412 |
| Frozen candidate 708, same HBQ bank | 0.293140 | 0.390412 |
| TTCW14 | 0.232532 | 0.364687 |

The expert target is the arithmetic mean only when exactly two finite expert
CREATIVITY ratings exist. The nonexpert target is the median of available finite
nonexpert CREATIVITY ratings. These remain separate constructs. Across the 32
planned works, expert and nonexpert target availability is 29 and 28 respectively.
Finite rating availability does not establish distinct-rater independence.

The saved marginal correlations use different available cohorts and are retained
in the aggregate. They must not replace the matched comparison above or be read
as an unmatched leaderboard.

## Conditional sensitivity

The following signed contrasts are HBQ minus TTCW14 on the same 19 paired works.
Historical and candidate contrasts are identical because their scores are equal.

| Human-reference axis | Difference in rho | Conditional 2.5/97.5 percentile range |
| --- | ---: | ---: |
| Expert mean-of-two | 0.060608 | [-0.410391, 0.540865] |
| Nonexpert median | 0.025724 | [-0.324648, 0.398170] |

Both ranges include zero. They come from 2,000 joint work-tuple draws with
replacement, seed 20261030, preserving duplicate multiplicity and fixed source
order. Every eligible contrast has 2,000 defined draws and zero undefined or
discarded draws. Historical-minus-candidate ranges are [0, 0]. These are
**conditional work-exchangeability sensitivity ranges**, not population
confidence intervals, nominal coverage results or cluster-aware uncertainty.
They do not establish superiority, causation or generalization.

## Inference budget held constant for policy rescoring

Historical CWR scoring and frozen708 use identical native verdict banks and share
the same inference history, including retained failures. The candidate adds no
model judgments. This holds inference expenditure constant by identity of the
underlying evidence, rather than by equating request counts across methods.

All 27 complete banks from the fixed 32-work cohort are included; five incomplete
banks remain unavailable. The candidate changed no eligible bank. This is a
paired scoring-policy result with 27 underlying banks, without additional native
replication. Equal-budget comparisons between CWR and external judging methods
remain unmeasured. Absolute token totals and deterministic processing costs are
not newly measured by this interpretation.

## Coverage and retained failures

The frozen plan has 736 logical request positions: 22 HBQ requests and one TTCW14
request per work. A complete HBQ raw bank contains 170 leaves. The final ledger
retains 730 accepted and 6 unadmitted/no-resend positions: HBQ has 698 accepted plus
6 unadmitted of 704; TTCW14 has 32 accepted requests. Historical failures were
retained and were not resent. The original consumer separately checked 734
retained raw headers and the full 736-position disposition ledger.

HBQ has 27 complete, scored banks and 5 incomplete banks. TTCW14 has 26 complete
numeric scores and 6 partial-abstention cases without a complete score. An accepted
request, a complete bank and a numeric score are distinct. Historical/candidate
scores use 0–100; TTCW14 uses 0–1. No arm has a recorded floor or ceiling score.
All 27 available HBQ scores are distinct; TTCW14 has 6 distinct scores with 25 items
in ties. Coverage summaries retain all 32 recorded values, including recorded
missing-bank values; no new eligibility decision is made here.

## Scope and provenance

This is a fixed 32-work descriptive pilot using existing human references. No
people were recruited, manual labels created or judges trained. Historical and
candidate projections share admitted raw judgments; they are not independent
replication. The candidate is not promoted. No pairwise native judgments were
planned, and no random/length or other simple baseline is asserted measured.

Native contexts retain their original mixed historical qualifications. This
publication does not recertify historical executions as the current account with
all collection-model tools disabled. The final continuation completed its 180
requests; that closure does not erase earlier failures or imply global capacity.

Only aggregate metrics and hash/size commitments are published. Creative text,
quotes, individual human ratings, case/group/judge/account/native identities,
private paths and the current worklog are excluded. Regeneration requires the
private frozen inputs, original execution evidence, actual saved analysis return
and its saved conditional supplement. The publication projection adds no model
requests, new judge votes or native/scientific replay calls. This package does not
claim a standalone public regeneration pipeline or independent human validation.
