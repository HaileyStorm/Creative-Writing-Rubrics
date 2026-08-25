# Whole-poem architecture DSPy V6: aggregate result

This is an aggregate-only, provider-free publication of the V6 development-only optimization result. It publishes neither corpus text, prompts, raw responses, private paths, nor per-contact identifiers.

The run made 44 allocations, dispatches, and confirmed contacts: four proposal responses and 40 task responses. Its ten-word static export was identical to the baseline. All five mechanical metrics were 0/8: there were no allowed literal verdicts and no whole-evidence exact substrings across the 40 task responses.

A manual semantic rescore was more favorable but insufficient to rescue the run: default 7/8; trials 5/8, 6/8, 5/8, and 4/8 (with a possible generous 5/8 for the final trial). The complete-single-part N/A boundary was missed in all five relevant cases.

The formal result is `HARNESS_INVALID_OPTIMIZATION_NO_TRANSFER_NO_PROMOTION`. It authorizes no transfer, wording change, runtime DSPy use, or promotion.

The settled execution record commits to the run-level settlement and static export hashes below, but does **not** bind all 44 response hashes, trial selections, prompts, or provider settings. This is a material post-run provenance limitation, not a reason to infer missing material from this public package.

Run `python verify.py` to validate the deterministic public projection.
