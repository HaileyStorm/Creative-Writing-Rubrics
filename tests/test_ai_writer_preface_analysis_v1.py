"""Sealed-evidence regression checks for preface pilot analysis v1."""
from __future__ import annotations

import importlib.util
import json
import shutil
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


def test_analysis_does_not_compare_the_historical_registry_tree_to_live_files(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    original = analysis._bound_tree

    def bound_tree(path: Path, expected: object, label: str):
        if label == "HBQ registry":
            pytest.fail("analysis must resolve the hash-bound aggregate instead of the live registry tree")
        return original(path, expected, label)

    monkeypatch.setattr(analysis, "_bound_tree", bound_tree)
    analysis.analyze(PUBLIC, PRIVATE, CONT_PUBLIC, CONT_PRIVATE, tmp_path / "out")


def test_current_additive_registry_preserves_all_completed_historical_scores():
    assert analysis.verify_current_additive_rescoring(PUBLIC, PRIVATE, CONT_PUBLIC, CONT_PRIVATE) == {
        "sealed_cells_with_question_id_payload_prompt_parity": 24,
        "rescored_completed_cells_with_metric_parity": 22,
    }
