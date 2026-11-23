# HANNA repeatability score projection v2

The historical v2/v3 HANNA analyzers report a standard deviation of zero when
an item has fewer than two numeric scores. That value does not measure
repeatability. They also include it in the aggregate mean deviation. This
separate, provider-free projection keeps historical reports and analyzers
unchanged. It reports the number of observed and unscored or unobserved runs,
and gives a null sample standard deviation and range when fewer than two scores
are available. Aggregates include only defined values and disclose their item
count; incomplete items with at least two scores remain in those descriptive
aggregates and are identified by their completeness fields.

Given an existing `repeatability.json` or a v3 `summary.json` from the
repeatability phase, run:

```text
python projection.py PATH_TO_EXISTING_REPORT.json
```

The projection is printed to standard output. Save it to a **different** file if
needed: shell redirection to the input path can overwrite the input before the
program starts. The output contains item IDs and must be handled according to
the input's privacy restrictions. It includes a SHA-256 of the exact source
bytes, rejects duplicate JSON keys, non-finite numbers and malformed score
lists, and never writes the source report. A matching hash identifies bytes; it
does not authenticate their origin, prove native-run provenance, or establish
that any historical result is affected. This projection does not alter leaf
agreement, human alignment, or previously frozen results.
