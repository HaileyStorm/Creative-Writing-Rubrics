# Ox Alpha v9 accepted slice

This offline analysis describes the 327 valid verdicts Ox Alpha returned before
the v9 run stopped. They cover 82 of 135 batches across three stories. The
remaining 210 leaves stay missing: nothing is imputed and no partial story is
given a complete-story score.

## Headline

On the identical accepted leaves, Ox matched Grok on 86.5% (`κ = 0.684`) and
GPT-5.6 Sol on 70.0% (`κ = 0.471`). This is useful model-comparison evidence,
not human alignment: Grok agreeing more often with Ox does not make either one
the ground truth.

Ox confidence was informative within this slice. Against Grok, agreement rose
from 75.4% in the 0.60–0.79 bin to 92.6% at 0.80–0.89 and 95.9% at 0.90–1.00.
The seven results below 0.60 are too few to interpret. Mean confidence was also
higher on agreements than disagreements for both references.

Coverage was uneven: 160/179 leaves for `hanna-827`, 123/179 for `hanna-957`,
and 44/179 for `hanna-201`. That missingness is why the package reports only
leaf-level accepted-slice statistics. Within-batch position numbers are
descriptive and do not isolate a batching effect.

Quote handling behaved cleanly after normalization: 453 retained exact quotes
all occur verbatim in the supplied story or prompt, while 11 invalid generated
quote fields were converted to summaries by the recorded normalization policy.
Six batches were quarantined: four empty responses, one malformed response, and
one other non-524 provider failure.

`max` reasoning was requested from Ox Alpha but was not provider-attested. This
is a provenance note, not a score adjustment.

## Next test

Use a tiny clean polarity × batch-size successor with batch sizes 1 and 4. That
direct comparison is more useful than trying to infer polarity or batching from
this incomplete operational run.

## Reproduce

The analyzer reads external evidence only from explicit arguments and emits
aggregate, prose-free JSON:

```powershell
.venv\Scripts\python.exe evaluation-results\hbq-ox-alpha-v9-accepted-slice-v1\analyze.py `
  --ox-work <frozen-v9-work> `
  --gpt-root <fresh88-repair-artifacts> `
  --grok-root <verified-grok-work> `
  --input-root <three-story-input-root> `
  --output <new-empty-output>
```

The checked result is in `results/`. Its manifest binds the prose-free summary;
the summary in turn binds the frozen v9 contract/state, all 82 accepted Ox
records, and the six exact GPT/Grok verdict files.
