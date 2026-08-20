# Prompts

`judge/` is the HBQ-RS evaluation protocol: prefix, per-leaf binary questions, task decomposition, pairwise finalists, long-form and multimodal rules, and import validation.

`review/` is open-ended critique. Those families return findings only. If a score report is supplied, they must not contradict it or invent a replacement total.

There is no provider client in this repository. Render a prompt with `cwr render-judge` or by concatenating these files yourself.
