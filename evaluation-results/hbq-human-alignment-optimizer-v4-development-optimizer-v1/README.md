# HANNA v4 development optimizer

This development-only successor recomputes equal-group HANNA training endpoints from
verified persisted raw v4 native-subscription training cells. A private verifier must
attest each prepared root, intent, result, raw request/response hashes, and exact
request-to-frozen-prompt binding. It refuses caller aggregates, development and
confirmation cells, and any mismatch with frozen candidate/prompt/route bindings.

When Optuna is installed, it runs a deterministic grid search over the frozen five
candidates. DSPy constructs a development-only `Predict` program that carries exact
parent bytes and frozen training diagnostics into a versioned descendant. This
package does not configure or invoke an LM; an explicit development caller must do
so, and the resulting bytes still pass descendant-lineage validation. DSPy is never
imported by runtime/evaluation packages. The routes are explicitly XAI Grok Build subscription
and OpenAI Codex/ChatGPT subscription; Codex is never relabelled as an OpenAI API
route. No output is an empirical alignment result, runtime selection, or confirmation
decision.
