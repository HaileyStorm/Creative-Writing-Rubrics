from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest

from _scoped_module_loader import load_module


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "evaluation-results" / "hbq-human-alignment-optimizer-v4-grok-sol-readout-v1"
compare = load_module(PACKAGE / "compare.py", name="hanna_v4_grok_sol_readout_v1")
DOCUMENTS = Path.home() / "Documents"
ROOTS = {
    "documents_root": DOCUMENTS,
    "queue_root": Path.home() / ".codex" / "state" / "model-work-queue",
    "frozen_successor_path": DOCUMENTS / "cwr-hanna-successor-fresh88-freeze-v4" / "frozen-successor-contract.json",
    "hanna_csv_path": DOCUMENTS / "cwr-hanna-pinned-data-282f275" / "hanna_stories_annotations.csv",
}


def test_pins_exact_verifiers_and_freezes_33_distinct_success_roots() -> None:
    assert hashlib.sha256(compare.EXEC_V3_PATH.read_bytes()).hexdigest() == compare.EXEC_V3_SHA256
    assert hashlib.sha256(compare.EXEC_V3_CONTRACT_PATH.read_bytes()).hexdigest() == compare.EXEC_V3_CONTRACT_SHA256
    assert hashlib.sha256(compare.ADMISSION_PATH.read_bytes()).hexdigest() == compare.ADMISSION_SHA256
    assert (
        hashlib.sha256(compare.ADMISSION_CONTRACT_PATH.read_bytes()).hexdigest()
        == compare.ADMISSION_CONTRACT_SHA256
    )
    assert compare.ANALYZER_CONTRACT_PATH == PACKAGE / "study-contract.json"
    specs = compare.default_pair_specs(DOCUMENTS)
    assert len(specs) == 33
    assert {spec["sol_cell_id"] for spec in specs} == set(compare.SOL_CELLS)
    assert len({str(spec["sol_execution_root"]) for spec in specs}) == 33
    assert set(compare.SOL_CELLS).isdisjoint(compare.EXCLUDED_TERMINAL_CELLS)
    assert compare.EXCLUDED_TERMINAL_CELLS == {
        "v4-cell-2eb4f20b3db15aac",
        "v4-cell-2333370999fb84f3",
    }
    assert specs[0]["sol_execution_root"].name == "cwr-hanna-v4-native-pilot-42ef2e9-v3"


def test_public_pair_requires_exact_prompt_schema_and_contains_no_prose() -> None:
    sol_row = {
        "cell_id": "sol",
        "item_id": "item",
        "candidate_id": "candidate",
        "task_payload_sha256": hashlib.sha256(b"prompt").hexdigest(),
        "response_schema_sha256": hashlib.sha256(b"schema").hexdigest(),
    }
    grok_row = {**sol_row, "cell_id": "grok"}
    scores = {dimension: 2.0 for dimension in compare.DIMENSIONS}
    sol = {
        "request": b"prompt",
        "schema": b"schema",
        "scores": scores,
        "identity": dict(compare.EXPECTED_ENDPOINT_IDENTITIES["sol"]),
        "evidence_status": "local_codex_lifecycle_verified_native_endpoint_contact_cardinality_unproven",
    }
    grok = {
        "request": b"prompt",
        "schema": b"schema",
        "scores": scores,
        "coverage": {dimension: True for dimension in compare.DIMENSIONS},
        "identity": dict(compare.EXPECTED_ENDPOINT_IDENTITIES["grok"]),
        "evidence_status": "admitted_grok_native_observation",
    }
    pair = compare._public_pair(sol_row=sol_row, grok_row=grok_row, sol=sol, grok=grok)
    assert set(pair["absolute_difference"].values()) == {0.0}
    assert pair["covered_for_paired_aggregate"] == pair["grok_coverage"]
    assert pair["uncovered_dimensions"] == []
    rendered = json.dumps(pair, sort_keys=True)
    assert "story_text" not in rendered
    assert all(token not in rendered for token in ("fixture evidence", "recurring motifs", "response evidence"))
    with pytest.raises(ValueError, match="exact prompt/schema pair is misassociated"):
        compare._public_pair(
            sol_row=sol_row, grok_row=grok_row,
            sol={**sol, "request": b"different"}, grok=grok,
        )


def test_coverage_excludes_uncovered_grok_dimensions_from_paired_aggregates() -> None:
    base = {
        "grok_scores": {dimension: 1.0 for dimension in compare.DIMENSIONS},
        "sol_local_lifecycle_scores": {dimension: 2.0 for dimension in compare.DIMENSIONS},
        "absolute_difference": {dimension: 1.0 for dimension in compare.DIMENSIONS},
        "covered_for_paired_aggregate": {dimension: True for dimension in compare.DIMENSIONS},
    }
    uncovered = json.loads(json.dumps(base))
    uncovered["absolute_difference"]["Empathy"] = 99.0
    uncovered["grok_scores"]["Empathy"] = 99.0
    uncovered["covered_for_paired_aggregate"]["Empathy"] = False
    aggregate = compare._aggregate_pairs([uncovered, base])
    assert aggregate["coverage_policy"] == (
        "exclude_uncovered_grok_dimensions_from_all_paired_aggregates"
    )
    assert aggregate["covered_pair_count_by_dimension"]["Empathy"] == 1
    assert aggregate["uncovered_pair_count_by_dimension"]["Empathy"] == 1
    assert aggregate["mean_absolute_difference_by_dimension_covered_only"]["Empathy"] == 1.0
    assert aggregate["mean_grok_score_by_dimension_covered_only"]["Empathy"] == 1.0
    assert aggregate["overall_covered_pair_dimension_count"] == 11


def test_contact_session_and_item_candidate_reuse_are_independently_rejected() -> None:
    contacts: set[tuple[str, str]] = set()
    sessions: set[tuple[str, str]] = set()
    compare._reserve_identity(
        {"provider": "provider", "contact_id": "contact-1", "session_id": "session-1"},
        provider_contacts=contacts, provider_sessions=sessions,
    )
    with pytest.raises(ValueError, match="duplicate provider/contact identity"):
        compare._reserve_identity(
            {"provider": "provider", "contact_id": "contact-1", "session_id": "session-2"},
            provider_contacts=contacts, provider_sessions=sessions,
        )
    with pytest.raises(ValueError, match="duplicate provider/session identity"):
        compare._reserve_identity(
            {"provider": "provider", "contact_id": "contact-2", "session_id": "session-1"},
            provider_contacts=contacts, provider_sessions=sessions,
        )
    item_candidates: set[tuple[str, str]] = set()
    compare._reserve_item_candidate("item", "candidate", item_candidates=item_candidates)
    with pytest.raises(ValueError, match="duplicate item/candidate pair"):
        compare._reserve_item_candidate("item", "candidate", item_candidates=item_candidates)


def test_duplicate_or_misassociated_pair_specs_fail_before_replay() -> None:
    specs = compare.default_pair_specs(DOCUMENTS)
    duplicate = [dict(spec) for spec in specs]
    duplicate[-1] = dict(duplicate[0])
    with pytest.raises(ValueError, match="duplicate or misassociated pair specifications"):
        compare.build_readout(pair_specs=duplicate, **ROOTS)
    wrong = [dict(spec) for spec in specs]
    wrong[0]["sol_cell_id"] = "v4-cell-not-frozen"
    with pytest.raises(ValueError, match="duplicate or misassociated pair specifications"):
        compare.build_readout(pair_specs=wrong, **ROOTS)
    wrong_root = [dict(spec) for spec in specs]
    wrong_root[0]["sol_execution_root"], wrong_root[1]["sol_execution_root"] = (
        wrong_root[1]["sol_execution_root"], wrong_root[0]["sol_execution_root"]
    )
    with pytest.raises(ValueError, match="duplicate or misassociated pair specifications"):
        compare.build_readout(pair_specs=wrong_root, **ROOTS)


def test_live_33_pair_provider_free_replay_is_public_safe_and_descriptive_only() -> None:
    readout = compare.build_readout(pair_specs=compare.default_pair_specs(DOCUMENTS), **ROOTS)
    assert readout["pair_count"] == 33 and len(readout["pairs"]) == 33
    assert readout["sol_evidence_ceiling"] == (
        "local_lifecycle_verified_native_endpoint_contact_cardinality_unproven"
    )
    assert readout["claims"] == {
        "selection": False,
        "substitution": False,
        "generalization": False,
        "provider_quality_ranking": False,
    }
    assert readout["story_text_included"] is False
    assert readout["aggregate"]["coverage_policy"] == (
        "exclude_uncovered_grok_dimensions_from_all_paired_aggregates"
    )
    assert readout["aggregate"]["covered_pair_count_by_dimension"] == {
        "Relevance": 27,
        "Coherence": 31,
        "Empathy": 29,
        "Surprise": 27,
        "Engagement": 31,
        "Complexity": 27,
    }
    assert readout["aggregate"]["uncovered_pair_count_by_dimension"] == {
        "Relevance": 6,
        "Coherence": 2,
        "Empathy": 4,
        "Surprise": 6,
        "Engagement": 2,
        "Complexity": 6,
    }
    assert readout["aggregate"]["mean_absolute_difference_by_dimension_covered_only"] == {
        "Relevance": 0.3556,
        "Coherence": 0.3226,
        "Empathy": 0.4879,
        "Surprise": 0.5667,
        "Engagement": 0.321,
        "Complexity": 0.613,
    }
    assert readout["aggregate"]["overall_covered_pair_dimension_count"] == 172
    assert readout["aggregate"]["overall_mean_absolute_difference_covered_only"] == 0.4392
    assert readout["inputs"] == {
        "frozen_successor_sha256": hashlib.sha256(ROOTS["frozen_successor_path"].read_bytes()).hexdigest(),
        "hanna_csv_sha256": hashlib.sha256(ROOTS["hanna_csv_path"].read_bytes()).hexdigest(),
        "exec_v3_sha256": compare.EXEC_V3_SHA256,
        "exec_v3_contract_sha256": compare.EXEC_V3_CONTRACT_SHA256,
        "admission_sha256": compare.ADMISSION_SHA256,
        "admission_contract_sha256": compare.ADMISSION_CONTRACT_SHA256,
        "analyzer_sha256": hashlib.sha256((PACKAGE / "compare.py").read_bytes()).hexdigest(),
        "analyzer_contract_sha256": hashlib.sha256(
            (PACKAGE / "study-contract.json").read_bytes()
        ).hexdigest(),
    }
    rendered = json.dumps(readout, sort_keys=True)
    forbidden = ("fixture evidence", "recurring motifs", "historical destination", "response evidence")
    assert all(token not in rendered for token in forbidden)
    assert all(pair["sol_native_endpoint_contact_cardinality"] == "unproven" for pair in readout["pairs"])
    result_path = PACKAGE / "result-33-pairs.json"
    result = json.loads(result_path.read_text(encoding="utf-8"))
    assert result_path.read_bytes() == compare.canonical(result)
    assert result == compare.publication_result(readout)
    assert all("grok_scores" not in pair for pair in result["pairs"])
    assert all("sol_local_lifecycle_scores" not in pair for pair in result["pairs"])
    assert "mean_grok_score_by_dimension_covered_only" not in result["aggregate"]
    assert "mean_sol_local_lifecycle_score_by_dimension_covered_only" not in result["aggregate"]
    assert result["endpoint_identities"] == compare.EXPECTED_ENDPOINT_IDENTITIES
    for key, value in (
        ("aggregate", {"fabricated": True}),
        ("claims", {**readout["claims"], "selection": True}),
        ("sol_evidence_ceiling", "invented"),
        ("inputs", {**readout["inputs"], "hanna_csv_sha256": "0" * 64}),
    ):
        fabricated = copy.deepcopy(readout)
        fabricated[key] = value
        with pytest.raises(ValueError, match="publication semantics drifted"):
            compare.publication_result(fabricated)
    wrong_endpoint = copy.deepcopy(readout)
    wrong_endpoint["pairs"][0]["grok_endpoint_identity"]["effective_model"] = "invented"
    with pytest.raises(ValueError, match="publication pair semantics drifted"):
        compare.publication_result(wrong_endpoint)
    wrong_difference = copy.deepcopy(readout)
    wrong_difference["pairs"][0]["absolute_difference"]["Relevance"] = 99.0
    with pytest.raises(ValueError, match="publication pair semantics drifted"):
        compare.publication_result(wrong_difference)
    duplicate_item_candidate = copy.deepcopy(readout)
    duplicate_item_candidate["pairs"][1]["item_id"] = duplicate_item_candidate["pairs"][0]["item_id"]
    duplicate_item_candidate["pairs"][1]["candidate_id"] = duplicate_item_candidate["pairs"][0][
        "candidate_id"
    ]
    with pytest.raises(ValueError, match="publication pair identities drifted"):
        compare.publication_result(duplicate_item_candidate)
