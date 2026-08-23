# Other lexical-overlap ownership v1

Frozen, public, synthetic, development-only current-wording screen for the
three remaining lexical-overlap findings in L2. It freezes no treatment and
contains no provider execution mode.

The geometry is fixed: three paired blocks, six semantic conditions per block,
two matched carriers, two singleton leaves, and three repeats: 216 planned
slots. Expected labels live only in the local ledger, never in provider-facing
prompts. `NOT_APPLICABLE` is completed but unscored; `CANNOT_ASSESS` is a
coverage control.

The prose-image block contains an active general-poetry / prose-poem-not-
applicable routing boundary rather than an unsupported cross-leaf failure
claim. The free-verse block contains both asymmetric directions. The visual block deliberately has
no cross-leaf opposite labels: it tests evidence ablation and shared visual
input delivery rather than manufacturing a distinction.

Visual fixture PNGs have opaque filenames and are generated deterministically by
`assets/generate_visual_fixtures.py`. Their bytes and manifest are bound by the
contract. The planner represents them as `image_inputs` (path, MIME type, and
SHA-256) and does not substitute a prose image description. A later separately
frozen execution successor must attach those exact PNG bytes as image input;
this provider-free package does not assert that the text-only production
renderer itself transports images.

Run `python run.py --dry-run` or `python run.py --render-plan`. Neither command
contacts a provider.
