# Optional whitespace grounding

`hbqrs.quote_grounding_v2.ground_hbq_quote()` locates a quote in unchanged source
text while allowing differences in whitespace runs. It is an opt-in source
grounding helper. Existing validation and scoring defaults remain unchanged.

```python
from hbqrs.quote_grounding_v2 import ground_hbq_quote

proof = ground_hbq_quote("A line continues.", artifact_text="A line\ncontinues.")
assert proof["state"] == "GROUNDED_WHITESPACE_ONLY"
raw_quote = proof["unique_raw_span"]  # "A line\ncontinues."
```

The policy collapses each consecutive run of characters for which Python's
`str.isspace()` is true to one ASCII space. It preserves leading and trailing
runs and every other character, including case, punctuation and order. Blank
quotes are rejected. The result records the runtime Unicode database version.

Artifact and context are searched separately. Supply only the scopes permitted
by the evaluation contract; the helper does not infer source permissions or
join text across a scope boundary. Each match carries the original raw span,
its hash, and zero-based half-open Unicode codepoint and UTF-8 byte offsets.
All locations are returned when a passage repeats. `unique_raw_span` is populated
only for one location; ambiguity is recorded without choosing or rejecting a
location. Returned spans contain source text and can be kept in local provenance
records.

`grounded` establishes a text match under this policy. It does not establish
whether a judgment about lineation, paragraphing or literary quality is correct.
The raw span retains the original layout for those assessments.

## Historical compatibility and derived views

The policy identifier is `hbq_unicode_whitespace_grounding_v2`. Importing this
module does not replace literal-substring validation, rewrite a saved response,
reclassify an old failure, replay a native receipt or call a scorer.

A caller that elects to validate a derived quote view must preserve the original
response and its native commitment. Record the new policy, original and derived
response hashes, mapped spans and projection proof separately. Only quote fields
may change, and all unrelated schema, evidence, applicability, abstention and
admission checks still apply. A derived response has its own hash; it must not be
presented as the model's original response or counted as another judgment.

Use the original policy for frozen results. A result produced under a newly
selected grounding policy needs its own version and a clear account of when
that policy was selected. This helper supplies no human validation, alignment
gain or authority to change a study's acceptance rules.
