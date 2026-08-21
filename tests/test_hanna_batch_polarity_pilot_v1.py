from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import os
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1] / "evaluation-results" / "hbq-hanna-batch-polarity-pilot-v1"


def _pilot():
    specification = importlib.util.spec_from_file_location("hanna_batch_polarity_pilot_v1", ROOT / "study.py")
    assert specification and specification.loader
    module = importlib.util.module_from_spec(specification)
    sys.modules[specification.name] = module
    specification.loader.exec_module(module)
    return module


def _digest(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


def _parent_binding(study, tmp_path):
    binding = study.fingerprint(study.CONTRACT_PATH)
    source = tmp_path / "source.md"; source.write_text("A source story.", encoding="utf-8")
    prompt = tmp_path / "prompt.md"; prompt.write_text("A source prompt.", encoding="utf-8")
    verdicts = tmp_path / "parent-verdicts.jsonl"
    verdicts.write_text("".join(json.dumps({"question_id": question_id, "verdict": "YES", "confidence": 0.8}) + "\n" for question_id in study._full_question_ids()), encoding="utf-8")
    return {
        "parent_runtime": {"root": "fixture", "files": {}, "sha256": _digest("fixture-runtime")},
        "parent_work": binding,
        "parent_matrix": binding,
        "parent_gate": binding,
        "parent_run": binding,
        "parent_score": binding,
        "parent_verdicts": study.fingerprint(verdicts),
        "parent_cell": {"item_id": "hanna-225", "artifact": study.fingerprint(source), "contexts": [study.fingerprint(prompt)]},
        "parent_verifier": {"sessions": [{"session_id_sha256": _digest(f"parent-{index}")} for index in range(6)]},
    }


def _prepared(study, tmp_path, monkeypatch):
    monkeypatch.setattr(study, "_parent_binding", lambda *_: _parent_binding(study, tmp_path))
    monkeypatch.setattr(study, "_valid_parent_runtime", lambda _: True)
    study.prepare(tmp_path / "parent-work", tmp_path / "parent-artifacts", tmp_path / "authority", tmp_path / "runtime", tmp_path / "work")
    return study.load_plan(tmp_path / "work")


def _evidence_for_cell(study, plan, cell, number: int):
    condition = study.condition_map()[cell["condition_id"]]
    chunks = study._chunks(cell["question_ids"], condition["batch_size"])
    calls = []
    for call_number, ids in enumerate(chunks, 1):
        verdicts = []
        for index, question_id in enumerate(ids):
            raw = "NO" if study.question_polarity(cell["condition_id"], question_id) == "negative_failure_condition" else "YES"
            if index == 0 and condition["scope"] == "focal":
                raw = "NOT_APPLICABLE"
            verdicts.append({"question_id": question_id, "verdict": raw, "confidence": 0.4 if index == 0 else 0.9})
        calls.append({
            "question_ids": ids,
            "session_id_sha256": _digest(f"session-{number}-{call_number}"),
            "prompt": study.rendered_prompt(plan, cell, ids),
            "prompt_sha256": _digest(study.rendered_prompt(plan, cell, ids)),
            "response": json.dumps(verdicts, sort_keys=True),
            "response_sha256": _digest(json.dumps(verdicts, sort_keys=True)),
            "verdicts": verdicts,
        })
    return {"condition_id": cell["condition_id"], "repetition": cell["repetition"], "calls": calls}


def test_preregistered_geometry_has_one_story_four_cells_three_stages_and_exact_new_call_totals():
    study = _pilot()
    contract = study.load_contract()
    cells = study.planned_cells()
    assert contract["status"] == "preregistered_development_only_no_empirical_results"
    assert len(study.focal_question_ids()) == 27
    assert sum(len(values) for values in study.mapping_sets().values()) == 28
    assert len(cells) == 12
    assert [sum(cell["new_calls"] for cell in cells if cell["stage"] == stage) for stage in (1, 2, 3)] == [60, 66, 66]
    assert sum(cell["new_calls"] for cell in cells) == 192
    assert next(cell for cell in cells if cell["condition_id"] == "global_positive_batch32" and cell["repetition"] == 1)["source"] == "verified_parent_repetition"
    assert all(len(cell["question_ids"]) == 179 for cell in cells if cell["condition_id"].startswith("global"))
    assert all(len(cell["question_ids"]) == 27 for cell in cells if cell["condition_id"].startswith("single"))


def test_pairs_are_exactly_owned_by_mapped_leaves_and_reverse_only_yes_no():
    study = _pilot()
    pairs = study.reviewed_pairs()
    assert [pair["question_id"] for pair in pairs] == study.focal_question_ids()
    assert len(pairs) == 27
    base = {"question_id": pairs[0]["question_id"], "verdict": "YES", "confidence": 0.5}
    assert study.canonicalize_verdict(base, "positive")["verdict"] == "YES"
    assert study.canonicalize_verdict(base, "negative_failure_condition")["verdict"] == "NO"
    assert study.canonicalize_verdict({**base, "verdict": "NO"}, "negative_failure_condition")["verdict"] == "YES"
    for state in ("NOT_APPLICABLE", "CANNOT_ASSESS"):
        assert study.canonicalize_verdict({**base, "verdict": state}, "negative_failure_condition")["verdict"] == state
    assert study.question_polarity("global_negative_batch32", pairs[0]["question_id"]) == "negative_failure_condition"
    assert study.question_polarity("global_negative_batch32", "core.task_and_brief_fidelity.intervention") == "positive"


def test_protocol_keeps_adaptive_confidence_as_a_calibration_gated_future_hypothesis_only():
    study = _pilot()
    adaptive = study.load_contract()["decision_policy"]["confidence_adaptive_repeats"]
    assert adaptive["status"] == "future_hypothesis_not_active"
    assert adaptive["requires"] == [
        "independent_confidence_calibration",
        "frozen_threshold_before_outcomes",
        "equal_call_budget_random_repeat_control",
        "equal_call_budget_uniform_repeat_control",
    ]
    assert "No canonical score" in adaptive["production"]
    assert "equal-budget" in adaptive["future_evaluation"]
    assert "never directly imitate global HANNA" in adaptive["custom_model_calibration"]


def test_prepare_replays_only_bound_parent_evidence_and_immutable_plan_rejects_tampering(tmp_path, monkeypatch):
    study = _pilot()
    plan = _prepared(study, tmp_path, monkeypatch)
    assert plan["parent"]["parent_cell"]["item_id"] == "hanna-225"
    assert plan["provider"] == {"provider": "codex", "model": "gpt-5.6-sol", "reasoning": "high", "fresh_sessions": True}
    assert plan["execution"]["remote_calls"] == "forbidden_until_a_distinct_executor_is_reviewed"
    path = tmp_path / "work" / "pilot-contract.json"
    tampered = json.loads(path.read_text(encoding="utf-8"))
    tampered["cells"][0]["condition_id"] = "forged"
    path.write_text(json.dumps(tampered), encoding="utf-8")
    with pytest.raises(ValueError, match="execution geometry"):
        study.load_plan(tmp_path / "work")


def test_parent_runtime_projection_rejects_current_runtime_drift_and_loads_exact_projection():
    study = _pilot()
    frozen_root = os.environ.get("CWR_FROZEN_PARENT_RUNTIME")
    parent_work = os.environ.get("CWR_FRESH88_PARENT_WORK")
    if not frozen_root or not parent_work:
        pytest.skip("requires explicit local frozen-parent runtime and fresh88 work roots")
    frozen = Path(frozen_root)
    current = study.ROOT
    frozen_binding = study._parent_runtime_binding(frozen)
    current_binding = study._parent_runtime_binding(current)
    assert frozen_binding != current_binding
    assert study._valid_parent_runtime(frozen_binding)
    with study._frozen_parent_runtime(frozen) as parent:
        frozen_manifest = parent.runtime_manifest()
        study._route_parent_runtime_manifest(parent, Path(parent_work), frozen)
    with study._frozen_parent_runtime(current) as parent:
        current_manifest = parent.runtime_manifest()
        with pytest.raises(ValueError, match="does not byte-match"):
            study._route_parent_runtime_manifest(parent, Path(parent_work), current)
    assert frozen_manifest["sha256"] != current_manifest["sha256"]


def test_replay_enforces_exact_batches_sessions_and_parent_reuse_boundary(tmp_path, monkeypatch):
    study = _pilot()
    plan = _prepared(study, tmp_path, monkeypatch)
    cells = [cell for cell in plan["cells"] if cell["source"] == "new_provider_evidence"]
    rows = [_evidence_for_cell(study, plan, cell, number) for number, cell in enumerate(cells, 1)]
    verified = study.verify_evidence(plan, rows)
    assert len(verified) == 12
    first_negative = verified["global_negative_batch32:1"][0]
    assert first_negative["verdict"] == "YES"
    bad = json.loads(json.dumps(rows))
    bad[0]["calls"][0]["question_ids"] = ["forged"]
    with pytest.raises(ValueError, match="exact question batch"):
        study.verify_evidence(plan, bad)
    extra = rows + [{"condition_id": "global_positive_batch32", "repetition": 1, "calls": []}]
    with pytest.raises(ValueError, match="ordered complete prefix"):
        study.verify_evidence(plan, extra)


def test_metrics_are_development_only_with_kendall_bridge_and_confidence_stability_diagnostics(tmp_path, monkeypatch):
    study = _pilot()
    plan = _prepared(study, tmp_path, monkeypatch)
    rows = [_evidence_for_cell(study, plan, cell, number) for number, cell in enumerate((cell for cell in plan["cells"] if cell["source"] == "new_provider_evidence"), 1)]
    for row in rows:
        for call in row["calls"]:
            for verdict in call["verdicts"]:
                if verdict["verdict"] == "NOT_APPLICABLE":
                    verdict["verdict"] = "NO" if study.question_polarity(row["condition_id"], verdict["question_id"]) == "negative_failure_condition" else "YES"
            call["response"] = json.dumps(call["verdicts"], sort_keys=True)
            call["response_sha256"] = _digest(call["response"])
    result = study.metrics(plan, rows)
    assert result["recommendation"] is None and result["promotion"] == "forbidden"
    assert result["correlation_bridge"] == {"signed_kendall_tau_b": None, "absolute_kendall_tau_b": None, "spearman": None, "status": "unavailable_one_story"}
    assert result["confidence_by_stability"]["interpretation"] == "repeat-consensus diagnostic, not calibrated human truth"
    assert study.kendall_tau_b([1, 2, 3], [1, 2, 3]) == pytest.approx(1.0)
    assert study.kendall_tau_b([1, 1], [2, 2]) is None
    assert study.correlation_bridge([1, 2, 3], [3, 2, 1]) == {"signed_kendall_tau_b": -1.0, "absolute_kendall_tau_b": 1.0, "spearman": -1.0}


def test_rendered_request_response_replay_and_stage_gate_are_strict(tmp_path, monkeypatch):
    study = _pilot()
    plan = _prepared(study, tmp_path, monkeypatch)
    rows = [_evidence_for_cell(study, plan, cell, number) for number, cell in enumerate((cell for cell in plan["cells"] if cell["source"] == "new_provider_evidence"), 1)]
    for row in rows:
        for call in row["calls"]:
            for verdict in call["verdicts"]:
                if verdict["verdict"] == "NOT_APPLICABLE":
                    verdict["verdict"] = "NO" if study.question_polarity(row["condition_id"], verdict["question_id"]) == "negative_failure_condition" else "YES"
            call["response"] = json.dumps(call["verdicts"], sort_keys=True)
            call["response_sha256"] = _digest(call["response"])
    first = rows[0]["calls"][0]
    assert "A source story." in first["prompt"] and "A source prompt." in first["prompt"]
    assert "failure_question" not in first["prompt"]
    tampered = json.loads(json.dumps(rows))
    tampered[0]["calls"][0]["response"] = "[]"
    tampered[0]["calls"][0]["response_sha256"] = _digest("[]")
    with pytest.raises(ValueError, match="parsed response"):
        study.verify_evidence(plan, tampered)
    assert study.stage_gate(plan, rows[:3])["status"] == "stage_1_complete"
    assert study.stage_gate(plan, rows[:7])["status"] == "stage_2_stop_no_reproduced_signal"
    assert study.stage_gate(plan, rows)["status"] == "stage_3_complete_development_only"
    polarity_effect = json.loads(json.dumps(rows[:7]))
    for row in polarity_effect:
        if row["condition_id"] in {"global_negative_batch32", "single_negative_batch1"}:
            for call in row["calls"]:
                for verdict in call["verdicts"]:
                    if study.question_polarity(row["condition_id"], verdict["question_id"]) == "negative_failure_condition":
                        verdict["verdict"] = "YES"
                call["response"] = json.dumps(call["verdicts"], sort_keys=True)
                call["response_sha256"] = _digest(call["response"])
    assert study.stage_gate(plan, polarity_effect)["status"] == "stage_3_required_signal"


def test_package_has_no_provider_or_network_path_and_execute_fails_closed():
    study = _pilot()
    tree = ast.parse((ROOT / "study.py").read_text(encoding="utf-8"))
    imports = {alias.name.split(".")[0] for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names}
    imports |= {node.module.split(".")[0] for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module}
    assert not imports & {"requests", "httpx", "urllib", "socket", "subprocess"}
    with pytest.raises(RuntimeError, match="cannot make provider calls"):
        study.execute()
