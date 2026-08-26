"""Regression coverage for the Ox Alpha v8 full-scoring successor."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
from copy import deepcopy

import pytest

from hbqrs.paths import book_root
from tests import _ox_historical_runtime as historical_runtime


ROOT = book_root() / "evaluation-results" / "hbq-human-alignment-supplemental-providers-ox-alpha-v8"
V7_ROOT = Path(r"C:\Users\Haile\Documents\cwr-ox-alpha-v7-cap1-pilot-20260821-5870d76")


def load(name: str, filename: str, aliases: dict[str, object] | None = None):
    spec = importlib.util.spec_from_file_location(name, ROOT / filename)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    prior = {key: sys.modules.get(key) for key in aliases or {}}
    sys.modules[spec.name] = module
    sys.modules.update(aliases or {})
    try:
        spec.loader.exec_module(module)
    finally:
        for key, value in prior.items():
            if value is None:
                sys.modules.pop(key, None)
            else:
                sys.modules[key] = value
    return module


study = historical_runtime.install(load("ox_alpha_v8_study", "study.py"))
analysis = load("ox_alpha_v8_analysis", "analyze_pilot.py", {"study": study})
pilot = load("ox_alpha_v8_pilot", "run_pilot.py", {"study": study})


def task(item_id: str = "item") -> dict:
    return {"contract_version": 1, "contract_id": "hanna", "artifact_id": item_id, "context": {"artifact_kind": "story", "declared_scope": "complete", "completion_status": "complete", "background": ["prompt"], "constraints": ["respond"], "audience": ["reader"]}, "preferences": [], "priorities": [], "weighted_goals": [{"goal_id": "prompt_response", "atomic_question": "Does the story meaningfully respond to the prompt?", "weight": 2.0, "source": {"kind": "driving_prompt", "reference": "prompt", "exact_excerpt": "prompt"}, "applies_to": ["whole artifact"], "rationale": "signal"}], "binding_requirements": []}


def test_contract_freezes_exact_179_cap1_full_geometry():
    runtime = study.CONTRACT["runtime"]
    assert study.CONTRACT["selection"]["item_ids"] == ["hanna-827", "hanna-957", "hanna-201"]
    assert runtime["batch_size"] == 4
    assert runtime["expected_batches_per_item"] == 45
    assert runtime["maximum_logical_requests"] == runtime["maximum_physical_http_attempts"] == 135
    assert runtime["maximum_physical_http_attempts_per_logical_request"] == 1
    assert runtime["execution_mode"] == "serial"
    assert "quiescence" in runtime["serial_rationale"]


def test_compiler_fixture_is_exact_179_with_44x4_plus_3(tmp_path):
    path = tmp_path / "task.json"
    path.write_text(json.dumps(task()), encoding="utf-8")
    geometry = study.question_geometry(path)
    assert len(geometry["static_question_ids"]) == 178
    assert len(geometry["primary_question_ids"]) == 179
    assert [len(batch) for batch in geometry["primary_batches"]] == [4] * 44 + [3]
    assert [item for batch in geometry["primary_batches"] for item in batch] == geometry["primary_question_ids"]
    assert geometry["task_contract_descendant"]["weighted_goals"] == []


def test_successful_v7_root_reproves_three_distinct_unrecovered_cap1_passes():
    if not V7_ROOT.is_dir():
        pytest.skip("successful v7 root is not present")
    proof = study.v7_completion(V7_ROOT)
    assert proof["verification"]["status"] == "PASS"
    assert proof["cap1"] is True and proof["no_recovery"] is True
    assert [cell["question_count"] for cell in proof["cells"]] == [4, 4, 4]
    assert all(cell["raw_http_duration_ns"] < 150_000_000_000 for cell in proof["cells"])
    assert all(len(set(values)) == 3 for values in proof["global_ids"].values())
    assert proof["request_schema"] == "codex-nous-tool-free-judge-request-v2"


def test_parent_hash_drift_fails_closed(monkeypatch):
    changed = dict(study.V7_FILES)
    changed["study.py"] = "0" * 64
    monkeypatch.setattr(study, "V7_FILES", changed)
    with pytest.raises(ValueError, match="v7 parent file drifted"):
        study.parent_v7()


def test_public_output_disjointness_precedes_evidence_verification(monkeypatch, tmp_path):
    work, output = tmp_path / "work", tmp_path / "work" / "published"
    work.mkdir()
    frozen = {"zero_cost_proof": {"path": str(tmp_path / "proof.json"), "catalog": {"root": str(tmp_path / "catalog")}, "usage": {"root": str(tmp_path / "usage")}}, "v7_transport_success": {"root": str(tmp_path / "v7")}, "fresh88": {"sources": {"work": str(tmp_path / "fresh"), "authority": str(tmp_path / "authority"), "repair1_artifacts": str(tmp_path / "repair")}}, "cells": []}
    monkeypatch.setattr(analysis, "load_frozen", lambda _: frozen)
    monkeypatch.setattr(analysis, "verify_evidence", lambda *_: (_ for _ in ()).throw(AssertionError("must not verify")))
    with pytest.raises(ValueError, match="disjoint"):
        analysis.analyze(work, output)
    assert not output.exists()


def test_executor_is_serial_and_passes_cap1_to_every_cell(monkeypatch, tmp_path):
    source, prompt, task_path = tmp_path / "source.md", tmp_path / "prompt.md", tmp_path / "task.json"
    source.write_text("story", encoding="utf-8")
    prompt.write_text("prompt", encoding="utf-8")
    task_path.write_text(json.dumps(task()), encoding="utf-8")
    cells = [
        {"cell_id": "ox-alpha-v8-01", "item_id": "one", "primary_question_ids": ["q1"]},
        {"cell_id": "ox-alpha-v8-02", "item_id": "two", "primary_question_ids": ["q2"]},
    ]
    calls = []
    monkeypatch.setattr(pilot, "load_frozen", lambda _: {"cells": cells, "v7_transport_success": {"tree": {"files": 1, "sha256": "a" * 64}, "global_ids": {"session_id": ["s"], "receipt_id": ["r"], "logical_request_id": ["l"]}}})
    monkeypatch.setattr(pilot, "_invocation", lambda work, _: study.immutable_json(work / "pilot-invocation.json", {"test": True}))
    monkeypatch.setattr(pilot, "input_paths", lambda _: (source, prompt, task_path))
    monkeypatch.setattr(pilot, "run_judge", lambda **kwargs: (calls.append(kwargs), Path(kwargs["output_dir"]).mkdir(parents=True)))
    monkeypatch.setattr(analysis, "verify_run", lambda _work, _frozen, cell: {"cell": cell["cell_id"]})
    prior = sys.modules.get("analyze_pilot")
    sys.modules["analyze_pilot"] = analysis
    try:
        pilot.execute(tmp_path)
    finally:
        if prior is None:
            sys.modules.pop("analyze_pilot", None)
        else:
            sys.modules["analyze_pilot"] = prior
    assert [call["artifact_id"] for call in calls] == ["one", "two"]
    assert all(call["batch_size"] == 4 and call["batch_attempts"] == 1 and call["max_physical_http_attempts_per_logical_request"] == 1 and call["resume"] is False for call in calls)
    assert [json.loads(path.read_text(encoding="utf-8"))["status"] for path in sorted((tmp_path / "pilot-journal").glob("*.json"))] == ["completed", "completed"]


def _cell(number: int) -> dict:
    ids = [f"q-{number}-{index:03d}" for index in range(179)]
    return {
        "cell_id": f"ox-alpha-v8-{number:02d}", "item_id": f"item-{number}", "ordinal": number,
        "inputs": {"source.md": {"name": "source.md", "bytes": 1, "sha256": "a" * 64}, "prompt.md": {"name": "prompt.md", "bytes": 1, "sha256": "b" * 64}, "task-contract.json": {"name": "task-contract.json", "bytes": 1, "sha256": "c" * 64}},
        "paths": {"artifact": f"C:/external/{number}/source.md", "prompt": f"C:/external/{number}/prompt.md", "task_contract": f"C:/external/{number}/task-contract.json"},
        "primary_question_ids": ids, "primary_batches": [ids[index:index + 4] for index in range(0, 179, 4)], "static_question_ids": ids[:-1],
        "task_contract_descendant": {"weighted_goals": [], "marker": number},
        "gpt_reference": {"matrix_record": {"score": number}, "repair1_artifacts": {"run": {"sha256": "d" * 64}}, "primary_score": float(number), "static_ablation_score": float(number) - 0.25},
    }


@pytest.mark.parametrize(("label", "mutate"), [
    ("gpt primary score", lambda cell: cell["gpt_reference"].__setitem__("primary_score", -1.0)),
    ("gpt static score", lambda cell: cell["gpt_reference"].__setitem__("static_ablation_score", -1.0)),
    ("item metadata", lambda cell: cell.__setitem__("item_id", "substituted-item")),
    ("ordinal metadata", lambda cell: cell.__setitem__("ordinal", 99)),
    ("source path", lambda cell: cell["paths"].__setitem__("artifact", "C:/substituted/source.md")),
    ("source commitment", lambda cell: cell["inputs"]["source.md"].__setitem__("sha256", "f" * 64)),
    ("task descendant", lambda cell: cell["task_contract_descendant"].__setitem__("marker", "substituted")),
])
def test_load_frozen_reconstructs_every_fresh88_cell_field(monkeypatch, tmp_path, label, mutate):
    work, payload, expected_cells = _frozen_payload(monkeypatch, tmp_path)
    (work / study.FROZEN_NAME).write_text(json.dumps(payload), encoding="utf-8")
    assert study.load_frozen(work)["cells"] == expected_cells
    mutate(payload["cells"][0])
    (work / study.FROZEN_NAME).write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="exactly reconstruct"):
        study.load_frozen(work)


def _frozen_payload(monkeypatch, tmp_path):
    monkeypatch.setattr(study, "REPO_ROOT", tmp_path / "managed-repository")
    sources = {key: tmp_path / key for key in ("work", "authority", "repair1_artifacts")}
    for path in sources.values():
        path.mkdir()
    expected_cells = [_cell(number) for number in range(1, 4)]
    fresh = {"sources": {key: str(path.resolve()) for key, path in sources.items()}, "binding": "fresh88"}
    zero = {"path": str(tmp_path / "proof.json"), "fingerprint": {"name": "proof.json", "bytes": 1, "sha256": "e" * 64}, "catalog": {"root": str(tmp_path / "catalog"), "sealed_at": "2026-08-21T00:00:00+00:00"}, "usage": {"root": str(tmp_path / "usage"), "sealed_at": "2026-08-21T00:00:00+00:00"}}
    predecessor = {"root": str(tmp_path / "v7"), "tree": {"files": 3, "sha256": "f" * 64}, "global_ids": {"session_id": ["s1", "s2", "s3"], "receipt_id": ["r1", "r2", "r3"], "logical_request_id": ["l1", "l2", "l3"]}}
    runtime = {"preparer": {"name": "prepare_pilot.py", "bytes": 1, "sha256": "1" * 64}, "executor": {"name": "run_pilot.py", "bytes": 1, "sha256": "2" * 64}, "verifier": {"name": "analyze_pilot.py", "bytes": 1, "sha256": "3" * 64}}
    monkeypatch.setattr(study, "runtime_bindings", lambda: runtime)
    monkeypatch.setattr(study, "judge_assets", lambda: {})
    monkeypatch.setattr(study, "_zero_cost_proof", lambda _: zero)
    monkeypatch.setattr(study, "assert_fresh_at", lambda *_: None)
    monkeypatch.setattr(study, "v7_completion", lambda _: predecessor)
    monkeypatch.setattr(study, "parent_v2", lambda: type("V2", (), {"_fresh88_binding": staticmethod(lambda *_: {"binding": "fresh88"})})())
    monkeypatch.setattr(study, "_frozen_cells", lambda _: deepcopy(expected_cells))
    monkeypatch.setattr(study, "input_paths", lambda _: (tmp_path / "source.md", tmp_path / "prompt.md", tmp_path / "task.json"))
    payload = {"format_version": 1, "study_id": study.CONTRACT["study_id"], "frozen_before_execution": True, "study_contract": study.fingerprint(study.CONTRACT_PATH), "runtime": deepcopy(runtime), "judge_assets": {}, "fresh88": fresh, "zero_cost_proof": {**zero, "freshness_checked_at": "2026-08-21T00:00:00+00:00"}, "v7_transport_success": predecessor, "cells": deepcopy(expected_cells)}
    work = tmp_path / "private-root"
    work.mkdir()
    return work, payload, expected_cells


def test_load_frozen_rejects_executor_hash_drift(monkeypatch, tmp_path):
    work, payload, _ = _frozen_payload(monkeypatch, tmp_path)
    payload["runtime"]["executor"]["sha256"] = "0" * 64
    (work / study.FROZEN_NAME).write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="frozen contract binding"):
        study.load_frozen(work)


def test_load_frozen_rejects_external_root_overlap(monkeypatch, tmp_path):
    work, payload, _ = _frozen_payload(monkeypatch, tmp_path)
    payload["fresh88"]["sources"]["work"] = str(work)
    (work / study.FROZEN_NAME).write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="distinct and non-overlapping"):
        study.load_frozen(work)


@pytest.mark.parametrize(("label", "mutate"), [
    ("provider id", lambda contract: contract["provider"].__setitem__("provider_id", "paid_alpha")),
    ("model", lambda contract: contract["provider"].__setitem__("model", "paid/model")),
    ("reasoning", lambda contract: contract["provider"].__setitem__("reasoning", "high")),
    ("no purchase", lambda contract: contract["zero_cost"].__setitem__("no_purchase", False)),
    ("charge stop", lambda contract: contract["zero_cost"].__setitem__("stop_on_charge_signal", False)),
])
def test_contract_rejects_paid_or_drifted_provider_semantics(monkeypatch, tmp_path, label, mutate):
    contract = deepcopy(study.CONTRACT)
    mutate(contract)
    path = tmp_path / "study-contract.json"
    path.write_text(json.dumps(contract), encoding="utf-8")
    monkeypatch.setattr(study, "CONTRACT_PATH", path)
    with pytest.raises(ValueError, match="provider or no-purchase"):
        study.load_contract()
