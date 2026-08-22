# Supplemental-provider verifier v2

This is a verification-only successor for the historical supplemental-provider v1 runs.
It never generates, resumes, or relabels a run. It proves the complete pinned
88-run/528-checkpoint Grok development corpus against the immutable v1 invocation and
the historical source blobs at commit `44518ababfa9d6a89baeddff2afe5cf5ccfe4e8f`.

The v2 manifest binds a receipt-chain commitment, a hashed provider/phase root, the
historical generation bindings, this verifier's runtime binding, and its separate
verifier contract. The verifier must be committed and clean before it writes a manifest.

The package exists because the historical v1 analyzer is execution provenance and cannot
be rewritten to correct platform newline handling.
