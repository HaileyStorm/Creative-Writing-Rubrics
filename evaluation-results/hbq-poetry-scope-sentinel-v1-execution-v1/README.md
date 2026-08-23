# S1 poetry scope sentinel execution v1

This separately frozen zero-paid execution successor is bound to the public,
synthetic S1 poetry scope sentinel at `67bbf999719a7aa62036edcb1e0a7104a43f17bf`.
It has five leaves, four scope states, and three repeats: 60 singleton slots,
with at most three cumulative attempts each (180 sends maximum). The only route
is Codex `gpt-5.6-sol` at `high`; paid APIs and fallbacks are forbidden.

Expected verdicts, state labels, fixture identities, and oracle rationales stay
only in the private schedule outside CWR. Each CWR judge call receives public
synthetic poetry, explicit task/scope context, and one leaf in a private minimal
diagnostic bundle. The exact historical S1 freeze—including its haiku polarity
rejection—must validate before a run is prepared.

`--dry-run` renders all 60 prompts without contacting a provider. Execution
requires both explicit remote and owner-attested zero-incremental-charge flags.
Settlement accepts only exact prompt bytes or checkpoint CRLF normalized to the
frozen LF render; lone CR, reverse normalization, and other byte changes fail
closed. Results are aggregate-only and cannot promote a prompt, rubric, leaf,
ownership, split, or weight change.
