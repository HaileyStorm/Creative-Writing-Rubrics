# HANNA polarity paired analysis v1

Offline aggregate reanalysis of the completed `hanna-225` batch/polarity pilot.
It binds the sealed parent repetition and stages 1–3, then reports only counts,
scores, coverage, confidence, and HANNA-dimension aggregates. It does not copy
story text, prompts, raw model responses, or external paths into this package.
The primary comparison endpoint-aligns published 1–5 HANNA ratings as
`(mean - 1) / 4`; a `mean / 5` sensitivity view is also retained. The ordering
of positive, paired, and negative results is the same under both conventions.

The analysis is descriptive for one story. Same-polarity batch-32 controls do
not use an equal call budget, and the focal paired average did not beat focal
positive on this story. It makes no production recommendation.

Run `analyze.py` with the six stage roots, the parent verdict file, the pinned
HANNA CSV, and an output directory. Each may be supplied by its documented
command-line argument or `HBQ_HANNA_*` environment variable.
Replay currently remains bound to the original pilot's same-host paths because
the sealed source pilot validates those paths as well as their hashes.
