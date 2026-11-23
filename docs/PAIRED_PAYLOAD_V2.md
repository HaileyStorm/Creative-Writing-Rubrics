# Paired payload construction, v2

`hbqrs.paired_payload_v2.build_paired_payloads` is an opt-in, provider-free
constructor for a matched pair. It checks two existing v1 content-address
descriptors and reuse records, verifies each supplied UTF-8 artifact against its
descriptor, and requires all non-artifact descriptor fields to match. It emits
two canonical JSON task bodies with the same instruction and swapped texts, plus
an ordinary v1 paired-comparison commitment to their exact bytes. Identity
controls are based on identical supplied text under that common context.
Context matching uses the canonical JSON representation, so values such as
`true`, `1`, and `1.0` do not silently compare equal.

Supply two independently generated opaque 128-bit hexadecimal request IDs and
keep the AB/BA mapping private from the evaluator. Distinct IDs make the two
task bodies distinguishable even for identical texts; they are part of the
model-visible content and may themselves affect responses. They do not prove
independence, randomization, or lack of model bias. Save the mapping, descriptors,
source receipts, bodies, responses, and applicable parser policy under the
study's existing access and retention rules.

The task bytes are **not** a provider HTTP request. A caller must preserve and
verify how they are wrapped and actually sent, and must separately verify the
model, account, tools, attempts, provider outcome, source rights, and historical
receipt provenance. Hashes and caller-supplied descriptors do not authenticate
those claims. This constructor does not freeze a research cohort, establish
human alignment, or show that a judge received the intended text. The existing
v1 APIs and historical receipts are unchanged; v1 accepts arbitrary committed
request bytes and full evaluation addresses are not simply text hashes.
