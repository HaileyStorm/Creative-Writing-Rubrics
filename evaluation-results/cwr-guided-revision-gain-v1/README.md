# CWR-guided revision gain v1

This is a provider-free execution scaffold for a small development study. Its
question is practical: when the same generator revises the same source once,
does bounded CWR feedback outperform an otherwise matched generic revision
request under blinded, non-CWR endpoint measures?

The public package deliberately contains no source-story or originating-HANNA
prompt prose, model output, or provider-native transport receipt. It pins the parent frozen-run-contract SHA-256 and
every one of the ten source/prompt fingerprints, selects six by a lexical rule
before execution, and holds four back. A separately authorized local work root
can freeze only those already-pinned fingerprints; it never copies source text
into this package.

## Frozen design

- First cycle: six sources, Grok 4.6 and GPT-5.6 Sol for every source; DeepSeek
  V4 Flash and GPT-5.6 Luna for the two predeclared breadth sources. Each cell
  has one `cwr_guided` and one `generic_no_feedback` descendant.
- Second cycle: only the same two breadth sources, using the same four
  generators and two guidance arms. It is predeclared, not earned by a first
  cycle score.
- The fixed schedule therefore has 48 revision cells. There is no best-of-N,
  adaptive extension, selective retry, or score-based cell choice.
- CWR feedback is crossed in the planned design: Grok-generated descendants
  would receive Sol feedback, Sol-generated descendants would receive Grok;
  Flash would receive Sol and Luna would receive Grok. The current CWR
  feedback artifact is exact pre-composition input only: it does not contain a
  composed rubric/questions prompt, provider payload, or response schema.
  Both endpoint judges would score every anonymous scalar target; endpoint
  dispatch contains no comparison pairs.
- Both arms receive the same neutral base revision instruction. The only arm
  difference is that the guided arm also receives its frozen CWR feedback
  packet; the control arm receives no feedback packet.
- An immutable `revision-lineage.jsonl` records every source commitment,
  cycle-parent commitment, descendant bytes and SHA-256, instruction and
  feedback binding, declared route intent/profile, and sampler identity. An
  immutable `endpoint-lineage.jsonl` would record each
  blinded target, exact instrument bindings, judge identity, integer response,
  rationale, and two quotations grounded in the target text. These manifests
  are validated locally and never overwritten.
- CWR feedback uses a frozen three-finding / 360-word maximum packet. Both
  revision arms use the same frozen instructions. DeepSeek is pinned as
  `deepseek/deepseek-v4-flash-0731` at `max`.
- Blinded endpoint assessment uses self-contained genre-neutral compact and
  holistic instruments, not the earlier TPTAF prompts. Each emits scalar
  `overall` scores. The frozen geometry is 54 targets (48 descendants plus six
  baselines) × two judges × two measures = 216 calls in a deterministic
  anonymous balanced order. The primary outcome is a calculated,
  within-source/generator/cycle guided-minus-control scalar delta. Summaries
  are equal-weighted and reported separately for every judge × measure × scale:
  raw 1–5 and 1–7 values are never pooled. Cycle-two comparisons are labelled
  cumulative from their cycle-one parent, with child-minus-parent endpoint
  deltas retained separately for both guidance arms. This small development
  pilot retains raw paired rows and directional counts but does not estimate an
  uncertainty interval. CWR feedback and scores are process evidence, not the
  success measure.

This is a development pilot. It does not establish universal literary quality,
human agreement, or a claim that either endpoint model is a human substitute.

## Provider-free preparation

The external source root must be the established HANNA multisample work root
and contain `inputs/<item-id>/source.md` and `prompt.md`. This command reads
those files only to freeze their identifiers, byte counts, and SHA-256 values;
it makes no remote request and does not copy source text.

```powershell
python evaluation-results/cwr-guided-revision-gain-v1/study.py `
  --source-root C:\path\to\cwr-multisample-repeatability-v1-20260821-44518ab `
  --work-root C:\path\to\cwr-guided-revision-gain-v1-live `
  --freeze-inputs --validate --write-preview
```

`--write-preview` emits a no-source-prose accounting of the exact future CWR
feedback and revision-generation destinations, call counts (24 and 48),
payload composition, input commitments, instruction, CWR runtime, endpoint
instruments, and frozen schedules. After descendants are generated and their
immutable lineage manifest validates, `--revision-manifest <path>
--write-endpoint-preview` emits the separate post-generation endpoint disclosure
for all 216 blinded calls and exact target commitments. Each remote phase
requires its own separately reviewed acknowledgement. Persist the first as
`acknowledgement.json` and the endpoint one as
`endpoint-acknowledgement.json` in the work root; downstream lineage and gain
validation reject results unless the corresponding stored preview, hash, and
acknowledgement bind exactly. The route intent/profile records planned routes
only; it never proves transport, accepted model/reasoning, or execution. Any
executed-lineage or revision-gain promotion additionally requires an immutable
provider-native transport receipt binding request ID, status, accepted
model/reasoning, transmitted payload SHA-256, and returned response SHA-256.
For CWR feedback, promotion also requires the exact frozen composition
manifest plus actual provider payload and schema; they are intentionally
absent here. This scaffold therefore makes no provider request, execution, or
gain claim. The companion
`disclosure-preview.canonical.sha256` is the expected value: it hashes the
canonical UTF-8 JSON payload (sorted keys, compact separators, no trailing
newline), rather than the newline-terminated preview file. The study never changes billing,
credit-card, subscription, or account settings.
