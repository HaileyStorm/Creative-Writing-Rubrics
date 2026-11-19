# State what the synopsis evaluation is about

A supplied synopsis and the story it describes are different evaluation objects.
Use the existing task-contract context fields to identify the requested object
and operation. There is no `evaluand` schema property.

These invented examples use the same text and the same diagnostic question:

| Contract | Requested assessment |
| --- | --- |
| `delivered.contract.json` | The supplied title and synopsis as a completed textual artifact. No adaptation is requested. |
| `adaptation.contract.json` | Whether the narrative material explicitly described could be controlled at short-story length. This is prospective adaptation planning, not evaluation of an unseen finished work. |

`artifact_kind` and `declared_scope` identify the object; `background` and
`constraints` describe the operation and available evidence. Both contracts use
version 2 with no weighted goals or binding requirements. Those empty arrays
add no task questions or gates.

From this example directory, render either example with the current CLI:

```bash
cwr render-judge --bundle prose.short_story --artifact synopsis.txt \
  --artifact-id invented-synopsis --question-id form.prose.short_story.scope \
  --task-contract delivered.contract.json \
  --scope-compatibility-override delivered.scope-override.json
```

For the adaptation task, use the two `adaptation.*.json` files instead. Changing
the contract creates a different evaluation condition; do not reuse a prior
request or relabel a historical run.

The selected question asks whether cast, timespan, setting and subplot load are
controllable at short-story length. Rendering it in both examples exposes the
task distinction for review. It does not establish that this question or the
whole short-story bundle is suitable for synopsis evaluation. The catalog does
not automatically route `film_synopsis` to this bundle. These are direct-run
override fixtures, not a new automatic route or a new synopsis bundle.

Each override binds the exact contract bytes, artifact ID and bundle. Its
reviewer and decision values are explicitly invented render-fixture values;
they are not a real compatibility approval and must not be reused to launch a
judge. A real contracted run needs its own scope decision. An override records
a reviewed compatibility choice; it does not alter selected questions or prove
their literary suitability.

The renderer places context in its frozen evaluation-data block. Context does
not override judge instructions, prescribe a verdict or automatically make a
criterion active or inactive. In particular, these examples do not guarantee
`NOT_APPLICABLE` for one contract or a binary answer for the other. Canonical
question wording, evidence rules and weights remain unchanged.

`verify.py PUBLIC_CHECKOUT` validates both contracts and exercises the actual
offline `render-judge` CLI. It checks that the emitted question payloads match
and that the only prompt difference is the contract-context block. It makes
no provider request and does not write to the supplied checkout. The examples
prove schema/rendering behavior only, not model compliance, judgment quality
or improved agreement.
