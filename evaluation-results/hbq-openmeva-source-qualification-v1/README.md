# OpenMEVA human-reference lead

This is a source and feasibility assessment, not an admitted benchmark or a
completed CWR comparison. [Guan et al. (2021)](https://aclanthology.org/2021.acl-long.500/)
describe OpenMEVA, including manually rated generated stories from ROCStories
and WritingPrompts and automatically constructed coherence and perturbation
tests. The manual set could help evaluate short-form quality and coherence;
it is not a substitute for full-story or novel assessment.

The paper reports that annotators compared seven stories for a prompt and
gave overall quality ratings on a 1–5 scale. A human-written story and an
artificial negative served as controls. Assignments were excluded if the
human story received less than 4 or the negative more than 2; the authors
report excluding 38.7% of ROC and 75.4% of WritingPrompts assignments. They
report five valid ratings per generated story. These are author-reported
procedures, not proof that the ratings measure all dimensions of literary
quality or that retained raters are representative. The filtering rule can
shape the observed reference. The paper also says three experts reviewed the
annotations; that statement does not make every rating an independent expert
quality judgment.

The [author repository](https://github.com/thu-coai/OpenMEVA) links a
[Hugging Face repository](https://huggingface.co/datasets/Jiann/OpenMEVA/tree/5ee4fe59caafce625670f91d3983f5c1ddab8c1d)
whose public metadata reported revision `5ee4fe59caafce625670f91d3983f5c1ddab8c1d`
and these files on 2026-11-23 UTC:

| Repository path | Reported size in bytes | Reported Git object ID |
| --- | ---: | --- |
| `data/mans_data/mans_roc.json` | 466,830 | `ea422f8dba9a6589b5a937aefd69c97a169cb024` |
| `data/mans_data/mans_wp.json` | 1,524,725 | `d5a00b9b9b458459af20f4f9cb2aec61265b9845` |

The paper calls its manual and automatic sets MANS and AUTOS; the GitHub
README uses MAGS and ACTS, while the Hugging Face paths use MANS and AUTOS.
That naming difference alone does not establish exact version equivalence.
The GitHub README describes the manual data as stories with annotations, but
the actual file schema and a target-blind extraction route have not been
verified. File metadata and reported object IDs are not a content readback.

The inspected Hugging Face metadata had no declared license tag and no
license-named file among its listed paths; that does not prove that no terms
exist. Rights for the source stories, annotations and proposed use remain
unresolved. WritingPrompts is also used by other CWR study datasets, so
cross-dataset identity and prior-exposure checks are required rather than an
assumption of independence.

While reviewing the paper and repository documentation, this task saw short
example fragments, an example input, illustrative ratings and perturbation
examples. Their dataset identities have not been mapped. Treat those examples
as exposed and the remaining cohort's unused status as unknown; do not select
or claim an unseen confirmation set from this assessment. No manual-set JSON
files, individual dataset rating records or complete stories were downloaded
for this check. No CWR or comparator judgments were generated, and no model
provider was contacted. Collection, candidate promotion and human-reference
confirmation remain subject to the project's existing gates.
