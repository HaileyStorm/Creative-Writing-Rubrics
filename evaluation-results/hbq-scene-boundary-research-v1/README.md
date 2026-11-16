# Scene boundary declarations for research

`boundary.py` checks caller-declared scene spans against exact UTF-8 source
bytes and binds three question texts to the same context commitment. It is
a standalone, standard-library research tool. It does not change the active
rubric, historical observations, activation, verdicts, weights or scoring.

Run with Python 3.10 or later:

```text
python boundary.py --source source.txt --source-sha256 <lowercase-sha256> --declaration declaration.json --output new-result.json
python -B verify.py
```

The declaration is a JSON object containing `boundary_kind`, `preceding`,
`target`, `exit` and `following`. Each span is either `null` or an object with
integer `start`, integer `end` and lowercase `sha256`. Offsets count UTF-8
**bytes**, starting at zero, and `end` is exclusive. Hashes cover the exact
source or span bytes without newline or Unicode normalization. The exit must
be a nonempty suffix of the target. Ordered units may be separated by whitespace;
unassigned prose, overlapping units and offsets splitting a character fail.

`boundary_kind` is one of:

- `terminal`: a target and exit, optional predecessor, and no following span.
- `interior_supplied`: a target and exit, optional predecessor, and a following span.
- `interior_withheld`: a target and exit, optional predecessor, and no following span.
- `unspecified`: all spans are null; the source remains unsegmented.

A terminal assertion and a withheld-continuation assertion can describe identical
supplied bytes. This tool cannot prove which is true or identify literary scene
boundaries. An exit span is not automatically a sentence. Acceptance establishes
structural consistency only; an unspecified boundary does not establish usable
scene evidence. Actual prompt delivery, native execution and human validity are
outside this tool's scope. No provider contacts occur.

The output contains hashes, offsets, declarations and question bindings, not
source prose. These commitments can still identify known material; keep inputs
and outputs within their authorized access and publication scope. Output is
created exclusively and an existing path is never overwritten. The verification
command generates artificial text in a temporary directory inside the tool's
writable folder and removes that directory afterward; it requires no
research corpus, human ratings or private files.
