from __future__ import annotations

import json
import re

from hbqrs.paths import book_root


ROOT = book_root() / "evaluation-results" / "hbq-p1-discordance-audit-v7-public-result-v1"


def _result() -> dict:
    return json.loads((ROOT / "public-result.json").read_text(encoding="utf-8"))


def test_settled_v7_result_is_exactly_two_accepted_contacts_and_no_promotion() -> None:
    result = _result()

    assert set(result) == {
        "format_version",
        "study_id",
        "public_cwr_lineage",
        "public_scope",
        "settlement",
        "identity_evidence",
        "v6_and_canary_role",
        "promotion",
        "limitations",
        "source_bindings",
    }
    assert result["format_version"] == 1
    assert result["study_id"] == "hbq-p1-discordance-audit-v1"
    assert result["public_cwr_lineage"] == {
        "execution_runtime_commit": "a771ce3b0429e7b68e162b5734f86dc62d281a46"
    }
    assert result["public_scope"] == "aggregate_only"
    assert result["settlement"] == {
        "status": "SETTLED_AGGREGATE_ONLY",
        "planned_v7_study_review_contacts": 2,
        "accepted_v7_study_review_contacts": 2,
        "classification": "SAME_INPUT_VARIANCE",
        "classification_count": 1,
        "appendix_disposition": "FAILED_APPENDIX_RETIRED_NOT_REUSABLE",
    }
    assert result["identity_evidence"] == "requested_model_and_reasoning_only"
    assert result["v6_and_canary_role"] == "transport_diagnostics_non_votes"
    assert result["promotion"] == "none"
    assert result["limitations"] == [
        "Aggregate-only public projection: no fixture text, fixture aliases, expected labels, prompts, individual outcomes, model outputs, private evidence, paths, or provider/session/request metadata.",
        "The model and reasoning were requested rather than independently attested.",
        "The v6 run and versioned canaries are transport diagnostics, not study votes, and are excluded from the 2/2 settled v7 result.",
        "SAME_INPUT_VARIANCE is the settled classification for this one review, not a general causal explanation or an identical-outcome claim.",
        "The failed appendix is retired as reusable evidence for this issue.",
        "No prompt, rubric, leaf, ownership, split, or weight change follows. Promotion is none.",
    ]


def test_v7_source_bindings_are_exact_sha256_commitments_only() -> None:
    bindings = _result()["source_bindings"]

    assert bindings == {
        "adapter_contract_sha256": "7e562860ccf6a43750e2beeb6702cab773516f2246aad5fefe534e741d89f1c4",
        "adapter_evidence_sha256": "ec7083a10f8824e9128ee9fa8b8a0fe9b82a48f8ca714ab76063900b8eb4632f",
        "adapter_preflight_chain_sha256": "7e914d2381a875596081edbef8ba874cf60dcbb97d2f7e219e4f054680e472da",
        "settlement_sha256": "ce70e78cccb7b8e2d9e14dbfa0bc79b723ca0c5bb36ebe36f01ffe392d546b39",
        "public_aggregate_sha256": "ca227619eec52e4d671829d0e2b67d5be8e4f228e413e5c036af5377db993d1a",
    }
    assert all(re.fullmatch(r"[0-9a-f]{64}", value) for value in bindings.values())


def test_public_projection_excludes_private_execution_material_and_paths() -> None:
    payload = (ROOT / "public-result.json").read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    assert not re.search(r"[A-Za-z]:[\\/]", payload + readme)
    forbidden = ("fixture_alias", "expected_label", "raw_response", "session_id", "request_id", "slot_id")
    assert all(token not in payload for token in forbidden)
