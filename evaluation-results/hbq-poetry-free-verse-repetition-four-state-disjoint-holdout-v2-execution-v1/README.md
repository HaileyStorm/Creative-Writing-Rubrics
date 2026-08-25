# S1 v2 one-shot execution successor v1

This provider-free package derives a new preclaim root from the settled v2
frozen inputs by byte-exact copy. It binds the exact public v2 contract,
study, corpus, sealed-outcome commitment, dry manifest, and the reused v1
public-corpus commitment. It never regenerates or replaces the v2 frozen
inputs.

The contract specifies twelve future singleton OpenAI/Codex GPT-5.6 Sol/high
contacts: one fresh session and one physical attempt per slot, no resume,
retry, normalization, paid fallback, or automatic promotion. Snapshot, claim,
terminal, and settlement records are write-once. Existing run state is a hard
failure.

The CLI offers only validation, provider-free snapshot derivation, and a
provider-free preclaim. It deliberately has no live-execution switch until an
independent review opens that separate gate.
