from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile

import pytest

from tests import _historical_runtime_compat as historical_runtime
from hbqrs import compile_bundle, load_bundles, load_modules
from hbqrs.paths import book_root, bundles_path, registry_path


ROOT = book_root() / "evaluation-results" / "the-part-that-arrives-first-repeatability" / "batch-curve-v2"
SIZES = [1, 2, 4, 8, 12, 16, 24, 32, 48, 64, 96, 128, "all-in-one"]


def _json(name: str) -> dict:
    return json.loads((ROOT / name).read_text(encoding="utf-8"))


def _raw_harness():
    spec = importlib.util.spec_from_file_location("batch_curve_v2", ROOT / "batch_curve_harness.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _harness():
    module = _raw_harness()
    historical_runtime.allow_batch_curve_runner_drift(module, _json("study-contract.json"))
    return module


def _compiled():
    modules = load_modules(registry_path())
    bundle = next(item for item in load_bundles(bundles_path()) if item["bundle_id"] == "prose.short_story")
    return modules, compile_bundle(modules, bundle)


def test_frozen_contract_binds_every_execution_and_interpretation_field() -> None:
    harness, contract = _harness(), _json("study-contract.json")
    _, compiled = _compiled()
    with pytest.raises(ValueError, match="Frozen runner revision drifted"):
        _raw_harness().validate_contract(contract, compiled)
    harness.validate_contract(contract, compiled)
    assert contract["runtime"]["runner_revision_sha256"] != hashlib.sha256((book_root() / "src" / "hbqrs" / "runner.py").read_bytes()).hexdigest()
    assert contract["runtime"]["harness"]["sha256"] == hashlib.sha256((ROOT / "batch_curve_harness.py").read_bytes()).hexdigest()
    assert (ROOT / "study-contract.projection.sha256").read_text(encoding="ascii").strip() == harness.contract_projection_sha256(contract)
    for path, value in ((["runtime", "evidence_normalization_policy"], "changed"), (["screening", "stopping_rule"], "changed"), (["metrics", "repeatability", "formulas", "exact_all_three_leaf_agreement"], "changed"), (["recommendation_policy", "hard_cap"], "changed"), (["cross_format_empirical_protocol", "reporting"], "changed")):
        mutated = copy.deepcopy(contract)
        target = mutated
        for key in path[:-1]:
            target = target[key]
        target[path[-1]] = value
        with pytest.raises(ValueError, match="projection"):
            harness.validate_contract(mutated, compiled)
    drifted = copy.deepcopy(contract)
    drifted["runtime"]["harness"]["sha256"] = "0" * 64
    with pytest.raises(ValueError, match="projection"):
        harness.validate_contract(drifted, compiled)


def test_fixture_retains_strict_verdicts_evaluation_and_physical_batch_shapes() -> None:
    harness, contract = _harness(), _json("study-contract.json")
    _, compiled = _compiled()
    calls: list[dict] = []

    def endpoint(ids: list[str], context: dict) -> list[dict]:
        calls.append(context)
        return harness._fixture_verdicts(ids)

    journal = harness.run_offline_fixture(contract, compiled, endpoint)
    completed = harness.verify_journal(journal, contract)
    assert len(completed) == 39
    assert all(row["accepted_call_question_count"] == 178 and row["evaluation"]["canonical_coverage"] == 1.0 for row in completed)
    calls_24 = [row for row in journal if row.get("event") == "accepted_call" and row["size"] == 24]
    assert [len(row["question_ids"]) for row in calls_24] == ([24] * 7 + [10]) * 3
    assert all(row["verdicts_sha256"] == harness.sha256_value(row["verdicts"]) for row in calls_24)
    assert len({row["provider"]["session_id"] for row in journal if row.get("event") in {"accepted_call", "rejected_call"}}) == len(calls)


def test_fixture_retry_and_journal_adversaries_fail_closed() -> None:
    harness, contract = _harness(), _json("study-contract.json")
    _, compiled = _compiled()
    rejected = False

    def endpoint(ids: list[str], _context: dict) -> list[dict]:
        nonlocal rejected
        if not rejected:
            rejected = True
            return [{"question_id": ids[0]}]
        return harness._fixture_verdicts(ids)

    journal = harness.run_offline_fixture(contract, compiled, endpoint)
    assert len([row for row in journal if row.get("event") == "rejected_call"]) == 1
    assert harness.verify_journal(journal, contract)[0]["retry_count"] == 1
    reused = copy.deepcopy(journal)
    calls = [row for row in reused if row.get("event") in {"accepted_call", "rejected_call"}]
    calls[1]["provider"]["session_id"] = calls[0]["provider"]["session_id"]
    with pytest.raises(ValueError, match="Fresh-session"):
        harness.verify_journal(reused, contract)
    incomplete = [row for row in journal if not (row.get("event") == "completed" and row.get("sequence") == 39)]
    with pytest.raises(ValueError, match="terminal completion"):
        harness.verify_journal(incomplete, contract)
    missing_reason = copy.deepcopy(journal)
    next(row for row in missing_reason if row.get("event") == "rejected_call")["rejection_reason"] = ""
    with pytest.raises(ValueError, match="rejection reason"):
        harness.verify_journal(missing_reason, contract)
    interleaved = copy.deepcopy(journal)
    first_second = next(index for index, row in enumerate(interleaved) if row.get("sequence") == 2 and row.get("event") == "accepted_call")
    first_terminal = next(index for index, row in enumerate(interleaved) if row.get("sequence") == 1 and row.get("event") == "completed")
    interleaved.insert(first_terminal, interleaved.pop(first_second))
    with pytest.raises(ValueError, match="Completion"):
        harness.verify_journal(interleaved, contract)
    extra = copy.deepcopy(journal)
    extra.append(copy.deepcopy(next(row for row in journal if row.get("event") == "completed")))
    with pytest.raises(ValueError, match="extra or unexpected"):
        harness.verify_journal(extra, contract)
    reordered = copy.deepcopy(journal)
    positions = [index for index, row in enumerate(reordered) if row.get("sequence") == 1 and row.get("event") == "accepted_call"]
    reordered[positions[0]], reordered[positions[1]] = reordered[positions[1]], reordered[positions[0]]
    with pytest.raises(ValueError, match="ordinal"):
        harness.verify_journal(reordered, contract)
    malformed = copy.deepcopy(journal)
    call = next(row for row in malformed if row.get("event") == "accepted_call")
    call["size"] = 999
    with pytest.raises(ValueError, match="unexpected fields or does not bind"):
        harness.verify_journal(malformed, contract)
    for field, value in (("format_version", True), ("size", 24.0), ("repetition", True)):
        type_confused = copy.deepcopy(journal)
        type_confused[0][field] = value
        with pytest.raises(ValueError, match="Journal plan"):
            harness.verify_journal(type_confused, contract)
    type_confused_completion = copy.deepcopy(journal)
    next(
        row for row in type_confused_completion if row.get("event") == "completed"
    )["accepted_checkpoint_count"] = 1.0
    with pytest.raises(ValueError, match="Completion"):
        harness.verify_journal(type_confused_completion, contract)


def test_fixture_exact_quotes_must_be_grounded_in_frozen_source() -> None:
    harness, contract = _harness(), _json("study-contract.json")
    verdict = harness._fixture_verdicts(["leaf"])
    verdict[0]["evidence"] = [{"kind": "exact_quote", "reference": "story", "exact_quote": "not present in the frozen story", "summary": None}]
    source = (ROOT / contract["source"]["path"]).read_text(encoding="utf-8")
    with pytest.raises(ValueError, match="not grounded"):
        harness._strict_fixture_verdicts(verdict, ["leaf"], artifact_text=source)


def test_cap_requires_complete_verified_journal_receipts_and_deep_evidence(tmp_path: Path) -> None:
    harness, contract = _harness(), _json("study-contract.json")
    stack, ids = harness.exact_stack(contract), contract["runtime"]["frozen_question_ids"]
    _, compiled = _compiled()
    journal = harness.run_offline_fixture(contract, compiled, lambda batch, _: harness._fixture_verdicts(batch))
    for row in journal:
        if row.get("event") in {"accepted_call", "rejected_call"}:
            row["provider"] = {"configured_provider_kind": "codex_cli", "runner_provider_argument": "codex", "reported": {"provider": "openai", "model": "gpt-5.6-sol", "reasoning_effort": "high"}, "session_id": row["provider"]["session_id"]}
    evidence = tmp_path / "deep-validation.json"
    receipt = lambda session: {"configured_provider_kind": "codex_cli", "runner_provider_argument": "codex", "reported": {"provider": "openai", "model": "gpt-5.6-sol", "reasoning_effort": "high"}, "session_id": session}
    payload = {
        "format_version": 1, "kind": "hanna_batch_curve_deep_validation", "stack": stack, "size": 24,
        "item_ids": contract["deep_hanna_bracket_validation"]["frozen_item_ids"], "repetitions": 3,
        "journal_commitment_sha256": harness.sha256_value(journal),
        "cells": [{"item_id": item_id, "repetition": repetition, "provider_receipt": receipt(f"deep-{item_id}-{repetition}"), "result": {"screening_cell_success": True, "canonical_reproduction": True}} for item_id in contract["deep_hanna_bracket_validation"]["frozen_item_ids"] for repetition in range(1, 4)],
    }
    evidence.write_text(json.dumps(payload) + "\n", encoding="utf-8")
    proof = {"path": str(evidence), "bytes": evidence.stat().st_size, "sha256": hashlib.sha256(evidence.read_bytes()).hexdigest(), "status": "passed", "journal_commitment_sha256": harness.sha256_value(journal)}
    item = {"stack": stack, "status": "empirically_validated_successful", "deep_validation_evidence": proof, "requested_question_count": len(ids), "full_question_ids": ids, "sequence": 4, "size": 24, "journal_records": journal}
    assert harness.largest_validated_cap([item], stack, contract) == 24
    wrong_stack = dict(stack); wrong_stack["model"] = "wrong"
    with pytest.raises(ValueError, match="exactly match"):
        harness.largest_validated_cap([item], wrong_stack, contract)
    literal_confusions = (
        (("format_version",), True),
        (("format_version",), 1.0),
        (("size",), True),
        (("size",), 24.0),
        (("repetitions",), True),
        (("repetitions",), 3.0),
        (("cells", 0, "repetition"), True),
        (("cells", 0, "repetition"), 1.0),
        (("cells", 0, "result", "screening_cell_success"), 1),
        (("cells", 0, "result", "canonical_reproduction"), 1),
    )
    original_payload = copy.deepcopy(payload)
    for path, value in literal_confusions:
        malformed_payload = copy.deepcopy(original_payload)
        target = malformed_payload
        for key in path[:-1]:
            target = target[key]
        target[path[-1]] = value
        evidence.write_text(json.dumps(malformed_payload) + "\n", encoding="utf-8")
        proof.update({"bytes": evidence.stat().st_size, "sha256": hashlib.sha256(evidence.read_bytes()).hexdigest()})
        assert harness.largest_validated_cap([item], stack, contract) is None
    evidence.write_text(json.dumps(original_payload) + "\n", encoding="utf-8")
    proof.update({"bytes": evidence.stat().st_size, "sha256": hashlib.sha256(evidence.read_bytes()).hexdigest()})
    payload["cells"] = payload["cells"][:-1]
    evidence.write_text(json.dumps(payload) + "\n", encoding="utf-8")
    proof.update({"bytes": evidence.stat().st_size, "sha256": hashlib.sha256(evidence.read_bytes()).hexdigest()})
    assert harness.largest_validated_cap([item], stack, contract) is None
    item["journal_records"] = [row for row in journal if row.get("event") != "completed"]
    assert harness.largest_validated_cap([item], stack, contract) is None


def test_repeatability_and_every_declared_confidence_metric_fail_closed() -> None:
    harness, contract = _harness(), _json("study-contract.json")
    repetitions = [[{"question_id": question_id, "verdict": "YES", "confidence": .75, "canonical_observed_score": 91.0, "strict_schema_conformant": True, "exact_quote_grounded": True} for question_id in ("a", "b")] for _ in range(3)]
    metrics = harness.repeatability_metrics(repetitions)
    assert harness.screening_state(metrics, contract["decline_and_bracket"]["thresholds"]) == "screening_successful"
    bad = copy.deepcopy(repetitions); bad[0][0]["strict_schema_conformant"] = "true"
    with pytest.raises(ValueError, match="literal boolean"):
        harness.repeatability_metrics(bad)
    duplicate = copy.deepcopy(repetitions); duplicate[0][1]["question_id"] = "a"
    with pytest.raises(ValueError, match="ordered leaves"):
        harness.repeatability_metrics(duplicate)
    inconsistent = copy.deepcopy(repetitions); inconsistent[0][1]["canonical_observed_score"] = 80.0
    with pytest.raises(ValueError, match="consistent canonical work score"):
        harness.repeatability_metrics(inconsistent)
    invalid_metrics = dict(metrics); invalid_metrics["observed_score_standard_deviation"] = float("inf")
    with pytest.raises(ValueError, match="finite"):
        harness.screening_state(invalid_metrics, contract["decline_and_bracket"]["thresholds"])
    rows = [{"question_id": "a", "verdict": "YES", "assessed": True, "weight": 2, "confidence": .5, "canonical_leaf_score": 1}, {"question_id": "a", "verdict": "NO", "assessed": True, "weight": 2, "confidence": .9, "canonical_leaf_score": 0}, {"question_id": "a", "verdict": "YES", "assessed": True, "weight": 2, "confidence": .9, "canonical_leaf_score": 1}]
    diagnostics = harness.confidence_diagnostics(rows)
    assert {"confidence_weighted_repeat_agreement", "confidence_distribution", "stable_vs_flipping", "high_confidence_disagreement_mass"} <= set(diagnostics)
    assert diagnostics["high_confidence_disagreement_mass"] == 2
    for malformed in ({**rows[0], "confidence": None}, {**rows[0], "confidence": "0.5"}, {**rows[0], "confidence": 2.0}, {**rows[0], "assessed": "true"}):
        with pytest.raises(ValueError):
            harness.confidence_diagnostics([malformed])
    with pytest.raises(ValueError, match="assessed state"):
        harness.confidence_diagnostics([{**rows[0], "verdict": "CANNOT_ASSESS", "assessed": True}] * 3)


def test_generated_85_bundle_matrix_covers_every_size_remainder_and_independent_manual_selection(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    harness, matrix = _harness(), _json("offline-mechanism-matrix.json")
    modules, _ = _compiled()
    assert harness.offline_matrix(modules, load_bundles(bundles_path()))
    assert len(matrix["bundle_rows"]) == 85
    assert all(set(row["partition_shapes"]) == {str(size) for size in SIZES} and row["partition_reconstructs_order"] for row in matrix["bundle_rows"])
    assert all(stack["all_frozen_partition_shapes_reconstruct_order"] for stack in matrix["representative_manual_stacks"])
    checks = harness.manual_stack_fixture_checks(modules, load_bundles(bundles_path()))
    assert len(checks) == 8 and all(check["all_frozen_partition_shapes_reconstruct_order"] for check in checks)
    fixture = _json("manual-stack-fixtures.json")
    fixture["stacks"][1]["bundle_id"] = fixture["stacks"][0]["bundle_id"]
    (tmp_path / "manual-stack-fixtures.json").write_text(json.dumps(fixture), encoding="utf-8")
    monkeypatch.setattr(harness, "HERE", tmp_path)
    with pytest.raises(ValueError, match="invalid fields"):
        harness.manual_stack_fixture_checks(modules, load_bundles(bundles_path()))


def test_executable_no_call_path_writes_only_a_local_fixture_journal() -> None:
    harness = _harness()
    with tempfile.TemporaryDirectory() as temporary:
        journal_path = Path(temporary) / "fixture-journal.jsonl"
        journal = harness.execute_offline_contract(ROOT / "study-contract.json", journal_path)
        assert journal_path.is_file() and len([row for row in journal if row.get("event") == "completed"]) == 39
        assert all(row.get("provider", {}).get("kind") != "codex_cli" for row in journal)
