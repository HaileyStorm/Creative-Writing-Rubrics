# Proposed request-51 recovery amendment

Status: proposal only. This document grants no execution or rearm authority.

The [original attempt](baseline-contact-51-incident-v1.json) is terminal. Its saved response is truncated, malformed, and lacks terminal attestation; it cannot be promoted. The existing runner, collector, and admission contract also prohibit inserting a replacement into that failed run.

The proposed owner decision is to permit **one separately recorded new Grok attempt** for logical request 51, after a reviewed recovery implementation and fresh post-revocation zero-charge evidence. It includes rearming the existing Grok route through the reviewed arming path; it permits no billing change, paid fallback, model change, or additional retry.

The recovery implementation must use a separate derivative execution root and explicit replacement lineage. It must preserve all original evidence, the 50 settled requests, the failed attempt, and the frozen plan. The failed attempt remains excluded; the new result can contribute only one logical vote. It must never rewrite the original rejection or represent the new contact as recovery of the original response.

Frozen request bindings:

- Plan SHA-256: `edeadb93c485ba227153329b5ae420de1c9d08d95e920bac0635d197fd3dbd7f`.
- Prompt: 7,749 bytes; SHA-256 `bdebac06701c5e924ae7622419ce96ff91bf1ec3e2fc08229f8332d1686743b1`.
- Schema: 2,587 bytes; SHA-256 `1083ea9d8d810649371e654e33d6aeec1b0ba0c7a912428a013009ed8a35340a`.

Before contact, offline regression and independent review must verify unchanged payload bytes, preserved accepted checkpoints, explicit attempt lineage, no duplicate votes or identities, and the ordinary native terminal/schema/provenance gates. A new ambiguous outcome stops the recovery. No V17, WPB, earlier qualification, or other terminal attempt is included. Sol validation and the full 236-story TRAIN/DEV objective remain unchanged.

Implementation is not yet ready. Adopting this proposal changes the frozen execution policy; the current terminal boundary remains controlling until the owner explicitly adopts it.
