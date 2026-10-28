# Reader-reference results: Dryad DEV30 and Kyoto QSF12

Evidence summary captured 28 October 2026 (UTC).

These two completed reader-reference analyses give descriptive associations on their
selected story sets. They do not establish expert agreement, a method winner,
human-alignment gain, calibrated quality or candidate promotion. The sources and
constructs remain separate. This package copies existing aggregate measurements;
it adds no judgments, scoring, native replay, provider calls or fresh census.

## Dryad: selected exposed DEV30

The analysis uses 30 selected development stories and pooled reader means for
**well written** and **enjoyed**. The retained source reports 362 selected rating
events, with 10-13 ratings per story. Those counts do not establish distinct
participants. They do not support a population or crossed-rater interval, and the
unused confirmation set was not opened.

Native admission covers **808 of 810 planned packets**: 688 of 690 HBQ packets and
30 of 30 for each comparator. Complete HBQ banks yield 28 story scores. Holistic,
compact and Oregon each yield 30 numeric scores. TTCW has 30 complete request packets
but 29 numeric scores; one partial abstention supplies no complete scalar. All five
methods have numeric values on the same **27-story availability-selected common
set**. The correlations and tie counts below use that common 27 throughout.

| Method | Numeric stories /30 | Spearman rho: well written | Spearman rho: enjoyed | Distinct common-set scores | Tied pairs /351 |
|---|---:|---:|---:|---:|---:|
| HBQ |28|0.0641613|0.1966713|27|0|
| Holistic |30|0.3482541|0.3291075|3|237|
| Compact |30|0.4179899|0.3269726|2|301|
| Oregon |30|0.4686884|0.4430403|8|63|
| TTCW14 |29|0.1645693|0.2940288|8|56|

HBQ has finer observed score granularity. That does not establish stronger alignment
or calibration. Native scales differ: HBQ 0-100, holistic 1-7, compact 1-5, Oregon 6-36
and TTCW 0-1. Means on those scales are not a common-scale leaderboard. The JSON
retains the full available-set and common-set distributions and their denominators.

The retained paired contrasts use their own exact shared numeric sets, which must
not be mixed with the common 27 table. Each difference is HBQ rho minus comparator
rho on the stated shared set:

| Comparator | Shared numeric stories /30 | Difference: well written | Difference: enjoyed |
|---|---:|---:|---:|
| Holistic |28|-0.2703109|-0.1184324|
| Compact |28|-0.3532717|-0.1333726|
| Oregon |28|-0.4794512|-0.3035358|
| TTCW14 |27|-0.1004079|-0.0973575|

All frozen Dryad common-set and contrast interpretations remain **inconclusive**
with informative, arm-dependent availability. The point estimates are still
availability-conditioned descriptions. Conditional resampling does not account for
unobserved outcomes or establish population uncertainty. Undefined bootstrap draws
were retained without redraw; the aggregate preserves their counts. No confidence
intervals or universal missing-outcome ranges are presented as confidence intervals
here. These results provide no winner or intervention-gain claim.

## Kyoto: fixed 12 stories across three topics

The selected reference contains **12 stories across three topics**. The outcomes
are reader **enjoyment** and **pleasing style**, not expert or broad-quality labels.
There are 321 admitted and 3 rejected native packets of 324 planned, and 72 method-by-
story profile cells across six methods. The profile cells are not 72 new judgments
or reader votes; the ladder candidate reuses the HBQ parent packets and adds zero
native packets. This is neither a 36-story analysis nor an expert-population result.

Both reader axes have 12 observed story means. The source's valid-rater counters
sum to 115 recorded responses per axis; rater identities do not establish 115 distinct
people. Historical preprocessing and exclusion counts remain partly unknown.

The primary correlations require the **same full 12** stories. HBQ, TTCW and the
lexical controls have all 12 values, so these primary points are available and
**are not attrition-inconclusive**. No confidence interval was estimated.

| Method or control | Full 12 rho: enjoyment | Full 12 rho: pleasing style |
|---|---:|---:|
| HBQ |-0.0070053|-0.0736847|
| Ladder candidate |-0.0070053|-0.0736847|
| TTCW14 |0.2234169|0.1882845|
| Lexical token count |0.8210526|0.6274175|
| Raw type/token ratio |0.0455342|0.0000000|
| Constant zero |Undefined constant vector|Undefined constant vector|
| Holistic, compact, Oregon |Primary unavailable: 11 values each|Primary unavailable: 11 values each|

HBQ minus TTCW primary rho differences are -0.2304222 for enjoyment and -0.2619692 for
pleasing style. Both use the complete 12. Secondary 11-story diagnostics cannot
replace a missing primary 12 result for holistic, compact or Oregon. Token count's
larger observed association is descriptive; it does not show that changing length
causes better reader outcomes or establishes a quality method.

| Method | Numeric stories /12 | Distinct scores | Tied pairs /available pairs |
|---|---:|---:|---:|
| HBQ |12|12|0/66|
| Ladder candidate |12|12|0/66|
| TTCW14 |12|7|6/66|
| Holistic |11|3|21/55|
| Compact |11|2|25/55|
| Oregon |11|8|3/55|

Ladder and HBQ aggregate distributions and correlations match, with reported rho
differences of zero on both axes. These aggregate facts alone **do not prove exact
paired equality of all 12 story scores**. They establish no ladder gain or promotion.
The small selected set and three-topic structure do not support independent-story,
independent-reader or broader population uncertainty claims. No fitting, sign
selection, bootstrap or confidence interval was performed for these Kyoto points.

## Provenance, limits and reproduction

Structured execution lineage identifies collection generation 637 and its actual
owning joins. Frozen Dryad lineage captions name 618 and the Kyoto profile caption
says `POST618`. This derived package clarifies that lineage; it does not rewrite the
raw reports. Scientific conditions and completed analyses remain those recorded by
the retained receipts.

The source summary discloses that, after the frozen Kyoto condition was fixed,
source-only mapping incidentally encountered upstream aggregate ICC weights. Those
values were not returned to or used by this analysis lane; global prior use remains
unknown. That disclosure is not evidence of a fresh independent validation set.

The machine-readable aggregate retains all reported primary and common-set point
statistics, marginal/common distributions, paired contrast denominators, missingness,
undefined values and relevant limits. It omits bootstrap draw commitments and
confidence intervals. No multiplicity-adjusted comparison, human ceiling, causal
effect, unseen-story generalization or full-program completion is established.
No baseline or candidate changes.

`source_commitments` retains hashes and sizes without private paths. The package
contains no story text, per-story ratings, memberships, participant IDs, raw model
responses, account identity or native execution paths. The reviewed input summary
and its underlying research records remain private.

`regenerate.py` reproduces the aggregate from the exact reviewed summary:

```text
python -B regenerate.py --reader-results <reviewed-reader-aggregate.json> --output <new-output.json>
```

The script uses only the standard library, checks the input hash and creates a new
output without overwriting. It copies existing measurements and removes operational
metadata; it does not reconstruct native acceptance or recompute scientific results.
The full research program remains incomplete.
