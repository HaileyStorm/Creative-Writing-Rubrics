# Dryad full-HBQ packet

This package freezes a provider-free judging packet for the public Dryad TRAIN/DEV stories. It uses the full canonical `prose.short_story` question bank: 178 ordered questions (143 domain, 18 penalty, 17 supplemental, and no hard gates). It does not sample leaves, use a coarse proxy, add a task contract, or add a dynamic goal.

The packet stores a complete canonical question bank and a story index containing only opaque story IDs, partition, and text SHA-256. Story text remains in the already verified parent freeze and is not duplicated. All 236 public stories are referenced: 176 TRAIN and 60 DEV. Confirmation is rejected through the provenance-bound parent public loader before packet construction.

`source.py` has only three commands:

```text
python source.py prepare --freeze-root FROZEN_DRYAD_ROOT --output-root NEW_PACKET_ROOT
python source.py verify --freeze-root FROZEN_DRYAD_ROOT --output-root PACKET_ROOT
python source.py preview --freeze-root FROZEN_DRYAD_ROOT --opaque-story-id PUBLIC_STORY_ID
```

`preview` renders the complete unbatched question set through the current runner for Grok and Sol and requires byte-identical prompts. It is a local preview, not authorization for a single all-in-one request, batch, provider process, or provider call.

Creation requires the generator, contract, and parent public-loader bytes to be committed at HEAD. Provenance records their repository paths, hashes, and generator commit. Verification resolves that recorded commit, so advancing HEAD without changing those files does not invalidate the packet. Source verification may invoke read-only Git commands; it never launches a provider.

The contract sets `batch_size` to null, execution authority to false, metric eligibility to false, and provider process launches to 0. This package has no live provider surface. The canonical runner's direct Grok path still requires shared Broker/host-gate integration; exact response-schema support, empirical batch qualification, and a frozen analysis protocol are also prerequisites. No human-axis mapping is added. Human targets are absent from the packet; the parent loader performs its existing source-integrity verification.
