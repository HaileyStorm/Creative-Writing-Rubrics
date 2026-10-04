# P1b independent AI intent review preparation

The first complete independent-agent review is retained unchanged and summarized
in `review-summary-001.json`: eight families, 24 variants and 577 exact evidence
quotes validated. Missing or unsupported anchors, interpretive uncertainties and
three residual role-bearing clauses prevented automatic oracle admission. The
review shares the generator's model family and is not human validation. The
later filter correction does not rewrite that packet or review. The owner permits
separate descriptive baseline/comparator/repeat measurement of these immutable
stimuli, with no fixed synthetic labels or intended-defect success-rate claim.

`prepare_review.py` builds an immutable private review candidate from an explicitly selected accepted generation prefix. It uses the existing provider-free `verify_accepted` to replay frozen prompt/schema, account/job commitments, the family's own native receipt, response, mechanical validation and exact derived text bytes. It reads frozen code snapshots without importing the account helper, probing an account, generating text or contacting a provider. Active generation code and evidence remain unchanged.

```powershell
.venv\Scripts\python.exe -B evaluation-results\hbq-semantic-crossform-p1b-intent-v1\prepare_review.py --manifest <generation-freeze\manifest.json> --manifest-sha256 <exact-file-sha256> --results-dir <generation-results> --through-family 2 --output-root <fresh-private-review-directory> --dry-run
```

The prefix must be explicitly specified and every selected family must be settled and accepted. The prospective design stays eight families / 24 variants / sixteen declared comparisons. `families_outside_selected_prefix` describes selection only; it never asserts that the other families are untouched, complete or ready. Omitting `--dry-run` writes exclusively into a fresh destination outside the repository and retained inputs. Preparation grants no reviewer/provider-contact authority.

Give the reviewer only `reviewer/packet.json` or `reviewer/packet.md` plus `reviewer/response-schema.json`. These contain exact texts, shared work context, proposed anchor review aids, the neutral fresh creative brief and exact frozen canonical target semantics. Hash-derived opaque variant IDs and a deterministic hash-order permutation conceal generation role identities. Original/defect/legitimate roles, generation variant IDs, proposed intent notes, intended transformations and generator review notes stay in `private/role-map.json`. Do not send the private map, source generation prompts or generation responses to the reviewer. Complete role-bearing sentences are filtered from anchor metadata only; exact source anchors, removed sentences and source/proposal hashes remain in private lineage. An entirely filtered anchor stays explicitly unavailable and blocks automatic preservation/admission claims. Reviewers may reject proposed anchors. If explicit generation role IDs/markers appear in creative text or other reviewer material, preparation fails rather than altering creative text. Blinding removes supplied role metadata; a reviewer can still infer differences from the creative texts.

The fixed review schema requires every variant to receive explicit `supported`, `not_supported` or `uncertain` judgments for the criterion, quality suitability, neutral brief suitability and each proposed anchor, plus a local-issue assessment. Settled judgments need nonblank exact quoted evidence from that variant or shared context and an explanation. Whitespace-only quotes cannot satisfy evidence admission. Uncertainty may have no quote when the missing evidence itself prevents assessment. No unique winner or failure count is prescribed. Poem review allows plausible refrain, stillness, juxtaposition and circular architecture; work-segment review makes no whole-novel claim.

Role filtering recognizes underscore, space and hyphen spellings of target-defect and legitimate-style labels, plus target-descendant wording. Metadata filtering and visible creative-role checks share the same marker definition. Previously frozen packets and reviews retain their original bytes and any reported blinding limitations; a corrected preparation creates a separate descendant rather than rewriting that evidence.

`validate_review(packet, private_map, review, subset)` is the provider-free unblinding validator. Use the frozen schema-subset module and verify the packet/map artifact hashes against the review preparation manifest before calling it. It checks the response schema, packet binding, complete variant/anchor inventory and exact own-source quote substrings. Original and legitimate controls must support the criterion, quality, brief and all anchors without a local issue. The defect must fail the criterion, identify a quoted local issue and at least one affected proposed anchor, assess those anchors as failed and the remaining anchors as preserved. Any uncertain assessment, unsupported control, unlocalized defect, unresolved disagreement or absent declaration of generator independence blocks the admission candidate. Requiring a defect to be localized to a proposed anchor is conservative: an inadequately specified anchor list may require owner review or a new separately frozen review contract.

Unblinding retains the complete review's hash, role-specific blocking reasons, reviewer declaration and disagreements. Declared independence is not native provenance proof. Even a passing `oracle_admission_candidate` leaves `oracle_accepted=false` and `eligible_for_scoring=false`; the owner reviews semantic suitability, freezes independent review provenance and separately freezes scoring. AI review does not create human labels, population literary ground truth or candidate promotion.

```powershell
.venv\Scripts\python.exe -m pytest tests\test_semantic_fixture_review.py -q
```

Mocked source-replay tests exercise boundaries without claiming native execution. The owner's actual metadata/text/receipt dry-run supplies provider-free replay evidence for the selected prefix, not proof of reviewer quality or future model behavior.
