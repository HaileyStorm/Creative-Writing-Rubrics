# Saved poetry repetition: same-prompt repeatability

This descriptive follow-up examines the 24 saved judgments from the
[free-verse repetition treatment](../hbq-poetry-free-verse-repetition-treatment-v1-execution-v1-public-result-v1/README.md).
It adds no model calls or human labels. The original study's `NO_GO` decision
and absence of promotion remain unchanged.

The saved requests form eight groups of three with identical checkpointed
prompt bytes within each group. In each group, source and context hashes,
declared leaf and rubric commitments, model and reasoning settings also match;
the reported session IDs are distinct. These are retained metadata, not
independently authenticated provider, account or complete runtime evidence.

Across the eight groups, 20 of 24 within-group pairs agree on the four-state
verdict; six groups are unanimous and two are mixed. Each trio supplies three
pairs, so those comparisons reuse the same outputs and are not independent.
Six of the 20 agreeing pairs are `CANNOT_ASSESS`/`CANNOT_ASSESS`: agreement on
inability to assess is not successful assessment of the criterion. The full
four-state matrix is in [aggregate.json](aggregate.json), ordered by the saved
repeat labels rather than asserted execution chronology.

| Saved treatment and role | Groups | Unanimous groups | Agreeing pairs |
| --- | ---: | ---: | ---: |
| Candidate control | 3 | 3 | 9 / 9 |
| Candidate target | 1 | 1 | 3 / 3 |
| Current control | 3 | 2 | 7 / 9 |
| Current target | 1 | 0 | 1 / 3 |

These are very small, selected synthetic treatment cases. Stability is not
correctness: the original frozen control panel's disputed results still prevent
promotion. The data do not establish human alignment, a population reliability
rate, superiority, account identity or current provider quiescence.

The schedule stores zero placeholders instead of prompt hashes. Separately
checked checkpoint prompts differ byte-for-byte from the retained rendered
copies, but all 24 match after CRLF-to-LF conversion. Neither fact establishes
the exact bytes delivered to a provider; the prompt groups above use the saved
checkpoint bytes, without treating normalized copies as byte-identical.

## Reproduction

`analyze.py` prints the aggregate using a private request/leaf index, private
schedule, private terminal records and the retained run directories. Supply
them with `--index`, `--schedule`, `--terminals` and `--runs-root`. The script
pins the three index inputs and each checkpoint, checks membership and verdict
bindings, and reports aggregates only. It uses the index's separately checked
prompt and source commitments; it does not independently authenticate remote
execution. Authorized access to the retained private inputs is required. No
poem, prompt, response text, work identifier, session ID or individual verdict
is included in this package.

An independent local recount used per-group verdict frequencies rather than
the pair-enumeration calculation and reproduced the eight groups and 20 of 24
agreeing pairs. It does not add model votes or human validation.
