# TTCW common28 plot-resampling sensitivity

This post-result development analysis adds uncertainty sensitivity to the saved
[initial comparison](../hbq-sol-ttcw-initial-development-20261026/README.md) and
[source controls](../hbq-sol-ttcw-source-controls-20261026/README.md).
It uses their exact available 28 works across 12 plots and previously opened,
cached expert means and method scores. The fixed cohort and analysis recipe were
frozen locally before this new numerical run.

| Paired difference in expert Spearman correlation | Point | 95% plot-bootstrap percentile range |
| --- | ---: | ---: |
| HBQ minus TTCW14, primary | 0.289372 | 0.022982 to 0.615380 |
| HBQ minus raw type/token ratio, secondary control | -0.068833 | -0.195396 to 0.126485 |

The original points reproduced exactly: HBQ rho 0.711917, TTCW14 rho 0.422545
and raw type/token ratio rho 0.780750. The vocabulary control retains its
numerically higher point association. Its difference from HBQ varies across
the paired plot resamples.

The finite procedure draws 12 plot IDs with replacement 2,000 times using
Python's random.Random seed 20261030. Each selected plot contributes all its
available matched works; a repeated plot duplicates those work occurrences.
The methods and reference share every draw. Average ties are reranked within
each resample. Percentiles use sorted linear interpolation at p*(n-1).
Both differences had 2,000 defined draws and zero undefined draws; no draws
were replaced. Resampled work occurrences ranged from 19 to 35, representing
resampling of these same 28 works.

These are conditional percentile ranges under the plot-resampling assumption.
The analysis was specified after the initial results were observed and covers
only 12 clusters in an availability-selected cohort. Plot, generator, source
and missingness structure limit interpretation. It establishes no superiority,
causal effect, human-alignment improvement or population generalization.

The planned 36-work comparison still lacks eight outcomes, and the original
33-shared-work rule remains unmet. The original full36 pair bootstrap remains
not_estimated; its universal missing-outcome difference bounds [-2,2] are
unchanged and remain separate from these conditional ranges. No candidate is
promoted and this is no unused confirmation.

This run read only cached scalar summaries, cached type/token rational values
and explicit plot metadata. It made no model calls, native or scorer replays,
text reads, raw-rating-file reads, label creation, fitting, calibration, sign
changes or cohort reselection. Existing expert means summarize 42 binary ballots
per story; they are not 42 independent experts or direct preference votes.

report.json contains aggregate results. provenance.json commits the executed
private recipe, implementation and result without including story identities,
individual targets, text, native identities, account details or local paths.
Reproducing the exact numbers requires the retained private fixed-cohort inputs;
the sampling algorithm, seed, denominators and input commitments are disclosed
here. The broader research and release program remains incomplete.
