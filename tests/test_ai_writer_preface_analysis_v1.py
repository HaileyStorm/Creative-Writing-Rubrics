"""Sealed-evidence regression checks for preface pilot analysis v1."""
from __future__ import annotations

import importlib.util
import json
import shutil
from copy import deepcopy
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "evaluation-results" / "hbq-ai-writer-preface-v1-analysis-v1"
PRIVATE = Path(r"C:\Users\Haile\Documents\cwr-ai-preface-pilot-private-20260822")
PUBLIC = Path(r"C:\Users\Haile\Documents\cwr-ai-preface-pilot-public-20260822")
CONT_PRIVATE = Path(r"C:\Users\Haile\Documents\cwr-ai-preface-continuation-private-20260822")
CONT_PUBLIC = Path(r"C:\Users\Haile\Documents\cwr-ai-preface-continuation-public-20260822")

spec = importlib.util.spec_from_file_location("preface_analysis", PACKAGE / "analyze.py")
assert spec and spec.loader
analysis = importlib.util.module_from_spec(spec)
spec.loader.exec_module(analysis)


pytestmark = pytest.mark.skipif(not all(path.is_dir() for path in (PRIVATE, PUBLIC, CONT_PRIVATE, CONT_PUBLIC)), reason="sealed local pilot roots are unavailable")


def test_sealed_analysis_is_aggregate_only_and_deterministic(tmp_path: Path):
    first, second = tmp_path / "first", tmp_path / "second"
    analysis.analyze(PUBLIC, PRIVATE, CONT_PUBLIC, CONT_PRIVATE, first)
    analysis.analyze(PUBLIC, PRIVATE, CONT_PUBLIC, CONT_PRIVATE, second)
    assert (first / "summary.json").read_bytes() == (second / "summary.json").read_bytes()
    assert (first / "summary.json").read_bytes() == (PACKAGE / "results-pre-repair-chain" / "summary.json").read_bytes()
    text = (first / "summary.json").read_text(encoding="utf-8")
    assert '"item_id"' not in text and '"question_id"' not in text and '"session_id"' not in text
    assert "30201c7ed6d0010c" not in text and "C:\\Users" not in text
    assert analysis.verify_output(first)["study_id"] == "hbq-ai-writer-preface-v1-analysis-v1"
    summary = json.loads(text)
    for result in summary["primary"]["canonical_leaf_flips"].values():
        assert result["all_cross_arm_session_pair_count"] == result["same_session_pair_count"] + result["different_session_pair_count"]


def test_tampered_private_terminal_is_rejected(tmp_path: Path):
    copied = tmp_path / "private"
    shutil.copytree(PRIVATE, copied)
    target = copied / "cells" / "0001" / "terminal.json"
    target.write_text(target.read_text(encoding="utf-8").replace('"status": "completed"', '"status": "tampered"', 1), encoding="utf-8")
    with pytest.raises(ValueError, match="bound path|terminal"):
        analysis.analyze(PUBLIC, copied, CONT_PUBLIC, CONT_PRIVATE, tmp_path / "out")


def test_tampered_continuation_settlement_failure_set_is_rejected(tmp_path: Path):
    copied = tmp_path / "continuation-public"
    shutil.copytree(CONT_PUBLIC, copied)
    settlement = copied / "offline-settlement.json"
    value = json.loads(settlement.read_text(encoding="utf-8"))
    value["primary_analysis"]["suffix_terminal_failures"] = []
    settlement.write_text(json.dumps(value, sort_keys=True, separators=(",", ":")), encoding="utf-8")
    with pytest.raises(ValueError, match="settlement terminal failure set"):
        analysis.analyze(PUBLIC, PRIVATE, copied, CONT_PRIVATE, tmp_path / "out")


def test_reordered_verdict_ids_are_rejected_before_flip_math(tmp_path: Path):
    schedule = analysis.rows(PUBLIC / "pilot-schedule.jsonl")
    cell = schedule[0]
    source = PRIVATE / "cells" / "0001" / "terminal.json"
    terminal = json.loads(source.read_text(encoding="utf-8"))
    terminal["verdicts"] = list(reversed(terminal["verdicts"]))
    terminal["verdicts_sha256"] = analysis.sha_bytes(analysis.canonical(terminal["verdicts"]))
    mutated = tmp_path / "terminal.json"
    mutated.write_text(json.dumps(terminal, ensure_ascii=False), encoding="utf-8")
    expected_ids = [row["question_id"] for row in json.loads(source.read_text(encoding="utf-8"))["verdicts"]]
    public_terminal = {"private_terminal_sha256": analysis.sha_bytes(mutated.read_bytes()), "verdicts_sha256": terminal["verdicts_sha256"]}
    with pytest.raises(ValueError, match="IDs or ordering"):
        analysis._validated_completed(cell, mutated, public_terminal, expected_ids)


def test_bound_private_task_contract_hash_is_required():
    executor_binding = analysis.read_object(PUBLIC / "executor-binding.json")
    entry = next(value for value in executor_binding["inputs"] if value["item_id"] == "30201c7ed6d0010c")
    expected = dict(entry["task_contract"])
    expected["sha256"] = "0" * 64
    with pytest.raises(ValueError, match="task contract binding drifted"):
        analysis._bound_file(PRIVATE / "inputs" / entry["item_id"] / "task-contract.json", expected, "Pilot task contract")


def test_historical_registry_resolves_the_bound_277_module_aggregate():
    modules, authority = analysis._aggregate_bytes()
    historical = authority["historical_functional_reconstruction"]
    assert len(modules) == 277
    assert historical["aggregate"]["sha256"] == "578207ef59f127a0bd52e7f38a25b9629ca2cfcdd73f49c944d9eee0bcbde928"
    assert historical["identity"] == "functional_reconstruction_not_original_full_tree"


def test_historical_registry_snapshot_refuses_missing_or_wrong_content(tmp_path: Path):
    with pytest.raises(ValueError, match="snapshot is unavailable"):
        analysis._aggregate_bytes(tmp_path / "missing.json")
    wrong = tmp_path / "wrong.json"
    wrong.write_bytes(b"[]")
    with pytest.raises(ValueError, match="aggregate binding drifted"):
        analysis._aggregate_bytes(wrong)


def test_historical_scoring_bundle_resolves_from_the_pinned_git_snapshot():
    bundle = analysis._historical_bundle()
    authority = analysis.read_object(PACKAGE / "historical-registry-compatibility.json")
    historical = authority["historical_functional_reconstruction"]
    assert bundle["bundle_id"] == "prose.short_story"
    assert bundle["standard"] == {"id": "HBQ-RS", "version": "1.0.0"}
    assert historical["bundle"]["sha256"] == "7ea60d4fbc1b9992dce6496a0c2771fa817a80a9384a0532ac85034b279e9319"


def test_identity_only_book_evolution_permits_only_one_declared_addition():
    historical = [{"module_id": "example.historical", "standard": {"id": "HBQ-RS", "version": "1.0.0"}, "title": "Historical"}]
    addition = {"module_id": "example.addition", "standard": {"id": "HBQ-RS", "version": "1.2.0"}, "title": "Addition"}
    authority = {
        "standard_identity": {"id": "HBQ-RS", "historical_version": "1.0.0", "current_version": "1.2.0"},
        "addition": {"module_id": "example.addition", "canonical_json_sha256": analysis.sha_bytes(analysis.canonical(addition))},
    }
    current = [deepcopy(historical[0]), addition]
    current[0]["standard"]["version"] = "1.2.0"
    analysis._identity_only_book_evolution(historical, current, authority)
    changed = deepcopy(current)
    changed[0]["title"] = "Changed"
    with pytest.raises(ValueError, match="beyond standard.version"):
        analysis._identity_only_book_evolution(historical, changed, authority)


def test_current_bundle_permits_only_the_declared_standard_version_change():
    historical = {"standard": {"id": "HBQ-RS", "version": "1.0.0"}, "bundle_id": "prose.short_story", "title": "Short story"}
    current = deepcopy(historical)
    current["standard"]["version"] = "1.2.0"
    authority = {"standard_identity": {"id": "HBQ-RS", "historical_version": "1.0.0", "current_version": "1.2.0"}}
    analysis._identity_only_bundle_evolution(historical, current, authority)
    current["title"] = "Changed"
    with pytest.raises(ValueError, match="beyond standard.version"):
        analysis._identity_only_bundle_evolution(historical, current, authority)


def test_current_book_allows_only_exact_declared_repair_descendants():
    historical = [
        {"module_id": "example.unchanged", "standard": {"id": "HBQ-RS", "version": "1.0.0"}, "title": "Unchanged"},
        {"module_id": "example.repaired", "standard": {"id": "HBQ-RS", "version": "1.0.0"}, "title": "Before"},
    ]
    current = deepcopy(historical)
    current[0]["standard"]["version"] = "1.2.1"
    current[1]["standard"]["version"] = "1.2.1"
    current[1]["title"] = "After"
    addition = {"module_id": "example.addition", "standard": {"id": "HBQ-RS", "version": "1.2.1"}, "title": "Addition"}
    current.append(addition)
    authority = {
        "standard_identity": {"id": "HBQ-RS", "historical_version": "1.0.0", "current_version": "1.2.1"},
        "addition": {"module_id": "example.addition", "canonical_json_sha256": analysis.sha_bytes(analysis.canonical(addition))},
        "bounded_descendants": [{
            "module_id": "example.repaired",
            "historical_canonical_json_sha256": analysis.sha_bytes(analysis.canonical(historical[1])),
            "canonical_json_sha256": analysis.sha_bytes(analysis.canonical(current[1])),
            "historical_version": "1.0.0",
            "current_version": "1.2.1",
            "repair_lineage": "declared-test-repair",
        }],
    }
    analysis._bounded_current_book_evolution(historical, current, authority)
    changed = deepcopy(current)
    changed[0]["title"] = "Unexpected"
    with pytest.raises(ValueError, match="undeclared"):
        analysis._bounded_current_book_evolution(historical, changed, authority)


def test_current_book_is_a_bounded_successor_not_a_pilot_rescore():
    historical, authority = analysis._aggregate_bytes()
    current = analysis._current_book_modules(historical, authority)
    assert len(historical) == 277
    assert len(current) == 278
    assert authority["current_book"]["standard_identity"]["current_version"] == "1.2.1"
    assert len(authority["current_book"]["bounded_descendants"]) == 3
    assert analysis._current_bundle(authority, analysis._historical_bundle())["standard"] == {"id": "HBQ-RS", "version": "1.2.1"}


def test_archived_current_book_rescore_fails_closed_instead_of_substituting_a_book():
    archived = analysis.read_object(PACKAGE / "historical-registry-compatibility.json")["archived_scoring_replay"]
    assert archived["status"] == "unavailable_exact_1_2_0_snapshot_no_current_score_replay"
    assert "verify_current_book_rescoring" not in vars(analysis)
