# Fresh96 validation freeze v1

Provider-free construction of the 64 endpoint-neutral payloads: 32 public/open Fresh96 validation items times the fixed baseline and Descendant13 profiles. `study.py` reads only the committed public manifest and committed candidate assets; it never reads the private freeze.

`python study.py --output-root C:\path\fresh-root` writes the executor-facing `schedule.json`. Wrappers first call `validate_frozen_root(root)`; it admits only that exact schedule and returns its cells. The schedule contains outbound payload bytes for local-first per-endpoint disclosure and must not be published as a result artifact. Grok and Sol wrappers must use each `payload_base64` unchanged and return normalized projections to the paired analyzer.

This opens validation measurement only. It performs no provider work and cannot select, promote, pool endpoints, or claim generalization.
