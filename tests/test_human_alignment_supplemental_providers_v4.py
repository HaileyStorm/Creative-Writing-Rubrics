from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path

import pytest

from hbqrs.paths import book_root

ROOT = book_root() / "evaluation-results" / "hbq-human-alignment-supplemental-providers-v4"


def load():
    spec = importlib.util.spec_from_file_location("supplemental_hanna_v4_study", ROOT / "study.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


study = load()


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def input_file(path: Path, content: str) -> dict:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return study.fingerprint(path)


def static_v1_parent(tmp_path: Path) -> tuple[Path, dict]:
    source = tmp_path / "primary"
    rows = [{"item_id": f"item-{number}", "story_sha256": str(number)} for number in range(1, 5)]
    inputs = {}
    for row in rows:
        folder = source / "inputs" / "development" / row["item_id"]
        inputs[row["item_id"]] = {
            "source.md": input_file(folder / "source.md", row["item_id"]),
            "prompt.md": input_file(folder / "prompt.md", row["item_id"]),
            "task-contract.json": input_file(folder / "task-contract.json", row["item_id"]),
        }
    parent = tmp_path / "v1-work"
    value = {
        "study_id": study.CONTRACT["predecessors"]["v1"]["study_id"],
        "primary_work_dir": str(source),
        "selection": {"partitions": {"development": rows}, "selection": {"seed": 11}, "question_ids": list(range(20))},
        "input_commitments": {"development": inputs},
    }
    write_json(parent / "frozen-provider-contract.json", value)
    return parent, value


def failed_v2_fixture(monkeypatch, tmp_path: Path) -> Path:
    parent, _ = static_v1_parent(tmp_path)
    root = tmp_path / "failed-v2"
    frozen = {
        "study_id": study.CONTRACT["predecessors"]["v2"]["study_id"],
        "contract_sha256": study.CONTRACT["predecessors"]["v2"]["files"]["study-contract.json"],
        "parent_work_dir": str(parent),
        "parent_frozen": study.fingerprint(parent / "frozen-provider-contract.json"),
    }
    _, frozen["cells"] = study._static_v2_cells(frozen)
    write_json(root / "frozen-transport-contract.json", frozen)
    write_json(root / "pilot-execution-claim.json", {"claim": "closed"})
    write_json(root / "pilot-invocation.json", {"invocation": "closed"})
    write_json(root / "pilot-journal" / "0001-pilot-01.json", {"cell_id": "pilot-01", "status": "failed"})
    write_json(root / "runs" / "pilot" / "pilot-01" / "responses" / "rejected" / "batch-0001" / "attempt-0001.json", {"rejected": True})
    evidence = root / "runs" / "pilot" / "pilot-01" / "responses" / "batch-0001.attempt-0001.nous.evidence"
    failed_session = evidence / "session-failed"
    write_json(failed_session / "receipt.json", {"status": "failure"})
    (failed_session / "events.jsonl").parent.mkdir(parents=True, exist_ok=True)
    (failed_session / "events.jsonl").write_text("\n".join(json.dumps({"event_type": "http_attempt", "data": {"status": status}}) for status in (524, 524)), encoding="utf-8")
    (failed_session / "manifest.json").write_text("{}", encoding="utf-8")
    second_session = evidence / "session-precontact"
    for name in ("manifest.json", "request.json", "trace.json", "transport.json"):
        (second_session / name).parent.mkdir(parents=True, exist_ok=True)
        (second_session / name).write_text("{}", encoding="utf-8")
    commitments = {}
    for relative in study.CONTRACT["failed_v2"]["commitments"]:
        record = study.fingerprint(root / relative)
        commitments[relative] = {"bytes": record["bytes"], "sha256": record["sha256"]}
    tree = study._tree(evidence, set())
    changed = dict(study.CONTRACT)
    changed["failed_v2"] = {
        "commitments": commitments,
        "raw_evidence_tree": {"path": str(evidence.relative_to(root)).replace("\\", "/"), **tree, "excluded": []},
        "terminal_http_statuses": [524, 524],
    }
    monkeypatch.setattr(study, "CONTRACT", changed)
    return root


def test_contract_preserves_closed_batch_8_pilot_policy():
    assert study.CONTRACT["execution_status"].startswith("CLOSED_")
    assert study.CONTRACT["pilot_policy"] == {
        "cells": 3,
        "batch_size": 8,
        "batch_attempts": 1,
        "workers": 1,
        "timeout_seconds": 600,
        "maximum_completion_seconds_exclusive": 100,
        "success_rule": "Three sequential distinct-session 2xx completions; each has exactly one physical attempt, valid exact raw transport verification, zero recovery, and duration below 100 seconds.",
    }


def test_predecessor_identities_are_pinned_and_currently_match():
    observed = study.verify_predecessors()
    assert set(observed) == {"v1", "v2", "v3"}
    assert observed["v2"]["study.py"] == "2e738f5353a1b9959e803b3f51d24de4ee1d6a6051fd28c036c352e564a6e380"


def test_predecessor_identity_tamper_fails_closed(monkeypatch):
    changed = dict(study.CONTRACT)
    changed["predecessors"] = {**changed["predecessors"], "v3": {**changed["predecessors"]["v3"], "files": {**changed["predecessors"]["v3"]["files"], "study.py": "0" * 64}}}
    monkeypatch.setattr(study, "CONTRACT", changed)
    with pytest.raises(ValueError, match="v3 predecessor drifted"):
        study.verify_predecessors()


def test_static_v1_lineage_reconstructs_v2_cells_without_loading_predecessor_modules(tmp_path):
    parent, _ = static_v1_parent(tmp_path)
    v2 = {"parent_work_dir": str(parent), "parent_frozen": study.fingerprint(parent / "frozen-provider-contract.json")}
    _, cells = study._static_v2_cells(v2)
    assert [cell["cell_id"] for cell in cells] == ["pilot-01", "pilot-02", "pilot-03"]
    assert all(len(cell["question_ids"]) == 16 for cell in cells)
    assert len({cell["item_id"] for cell in cells}) == 3


def test_static_v1_lineage_rejects_input_byte_drift(tmp_path):
    parent, _ = static_v1_parent(tmp_path)
    v2 = {"parent_work_dir": str(parent), "parent_frozen": study.fingerprint(parent / "frozen-provider-contract.json")}
    folder = tmp_path / "primary" / "inputs" / "development" / "item-1"
    (folder / "source.md").write_text("changed", encoding="utf-8")
    with pytest.raises(ValueError, match="input bytes drifted"):
        study._static_v2_cells(v2)


def test_static_v1_lineage_rejects_duplicate_question_geometry(tmp_path):
    parent, value = static_v1_parent(tmp_path)
    value["selection"]["question_ids"][1] = value["selection"]["question_ids"][0]
    write_json(parent / "frozen-provider-contract.json", value)
    v2 = {"parent_work_dir": str(parent), "parent_frozen": study.fingerprint(parent / "frozen-provider-contract.json")}
    with pytest.raises(ValueError, match="cell geometry drifted"):
        study._static_v2_cells(v2)


def test_failed_v2_fixture_accepts_then_rejects_terminal_evidence_tamper(monkeypatch, tmp_path):
    root = failed_v2_fixture(monkeypatch, tmp_path)
    assert len(study.failed_v2_commitments(root)["cells"]) == 3
    evidence = root / study.CONTRACT["failed_v2"]["raw_evidence_tree"]["path"] / "session-failed" / "events.jsonl"
    evidence.write_text(json.dumps({"event_type": "http_attempt", "data": {"status": 200}}), encoding="utf-8")
    with pytest.raises(ValueError, match="raw evidence tree drifted"):
        study.failed_v2_commitments(root)


def test_immutable_json_is_idempotent_and_rejects_drift(tmp_path):
    path = tmp_path / "immutable.json"
    study.immutable_json(path, {"value": 1})
    original = path.read_bytes()
    study.immutable_json(path, {"value": 1})
    with pytest.raises(ValueError, match="Immutable record drifted"):
        study.immutable_json(path, {"value": 2})
    assert path.read_bytes() == original


def test_contract_loader_rejects_execution_closure_drift(monkeypatch, tmp_path):
    contract = json.loads((ROOT / "study-contract.json").read_text(encoding="utf-8"))
    contract["execution_status"] = "OPEN"
    path = tmp_path / "study-contract.json"; write_json(path, contract)
    monkeypatch.setattr(study, "CONTRACT_PATH", path)
    with pytest.raises(ValueError, match="execution closure drifted"):
        study.load_contract()


def test_freeze_is_provider_free_and_binds_only_fresh_root(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(study, "verify_predecessors", lambda: {"v1": {}, "v2": {}, "v3": {}})
    monkeypatch.setattr(study, "failed_v2_commitments", lambda root: calls.append(root) or {"work_dir": str(root)})
    monkeypatch.setattr(study, "runtime_bindings", lambda: {"runner": {"sha256": "r"}, "launcher": {"sha256": "l"}, "bridge": {"sha256": "b"}})
    fresh = tmp_path / "fresh"
    frozen = study.freeze_work(tmp_path / "failed-v2", fresh)
    assert calls == [tmp_path / "failed-v2"]
    assert frozen["provider_calls_made"] == 0
    assert frozen["runtime"]["bridge"]["sha256"] == "b"
    assert frozen["compatibility_snapshot"]["historical_cell_question_count"] == 16
    assert (fresh / "frozen-transport-contract.json").is_file()
    with pytest.raises(ValueError, match="fresh nonexistent"):
        study.freeze_work(tmp_path / "failed-v2", fresh)


def test_freeze_rejects_existing_empty_root_after_external_validation(monkeypatch, tmp_path):
    work = tmp_path / "orphan"; work.mkdir()
    calls = []
    monkeypatch.setattr(study, "verify_predecessors", lambda: calls.append("predecessors") or {})
    monkeypatch.setattr(study, "failed_v2_commitments", lambda _: calls.append("failed") or {})
    monkeypatch.setattr(study, "runtime_bindings", lambda: calls.append("runtime") or {})
    with pytest.raises(ValueError, match="fresh nonexistent"):
        study.freeze_work(tmp_path / "failed-v2", work)
    assert calls == ["predecessors", "failed", "runtime"]


def test_external_validation_failure_leaves_no_output_root(monkeypatch, tmp_path):
    work = tmp_path / "would-be-output"
    monkeypatch.setattr(study, "verify_predecessors", dict)
    monkeypatch.setattr(study, "failed_v2_commitments", lambda _: (_ for _ in ()).throw(ValueError("bad external evidence")))
    with pytest.raises(ValueError, match="bad external evidence"):
        study.freeze_work(tmp_path / "failed-v2", work)
    assert not work.exists()


def test_execution_has_no_open_surface():
    with pytest.raises(ValueError, match="execution is closed"):
        study.execution_is_closed()
    text = (ROOT / "study.py").read_text(encoding="utf-8")
    assert "from hbqrs" not in text and "import hbqrs" not in text and "run_judge" not in text


def test_failed_v2_commitments_are_checked_only_when_external_root_is_supplied():
    configured = os.environ.get("CWR_FAILED_V2_ROOT")
    if not configured:
        pytest.skip("set CWR_FAILED_V2_ROOT to validate the immutable external failed-v2 root")
    value = study.failed_v2_commitments(Path(configured))
    assert value["raw_evidence_tree"]["files"] == 7
    assert len(value["cells"]) == 3
