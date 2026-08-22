from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "evaluation-results" / "hbq-multisample-repeatability-v1-remainder-capacity-reset-successor-v2"


def _runner():
    spec = importlib.util.spec_from_file_location("capacity_reset_runner", PACKAGE / "run_capacity_reset.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _receipt(when: datetime) -> dict[str, object]:
    return {
        "kind": "external_current_capacity_evidence_v2",
        "provider": "codex",
        "model": "gpt-5.6-sol",
        "assertion": "capacity_available",
        "observed_at": when.isoformat(),
        "observation": {"surface": "native_codex_quota_surface", "reference": "visible current capacity reset"},
    }


def test_contract_keeps_the_exact_frozen_153_cell_schedule() -> None:
    runner = _runner()
    frozen = runner.contract()["schedule"]
    assert frozen == {
        "count": 153,
        "first_sequence": 178,
        "last_sequence": 330,
        "sha256": "96b91f124d2a889f4fa47b70d67c16604927f33928ca4ad5d302713c84f8f086",
    }


@pytest.mark.parametrize(
    ("path", "replacement"),
    [
        (("provider", "model"), "gpt-5.6-luna"),
        (("provider", "reasoning"), "max"),
        (("capacity_gate", "probe_authorizes_provider_contact"), True),
        (("supersedes", "scope"), "all protocol semantics"),
        (("runtime", "executor_present"), True),
    ],
)
def test_contract_rejects_provider_capacity_supersession_and_runtime_drift(monkeypatch: pytest.MonkeyPatch, path: tuple[str, str], replacement: object) -> None:
    runner = _runner()
    mutated = json.loads(runner.CONTRACT_PATH.read_text(encoding="utf-8"))
    mutated[path[0]][path[1]] = replacement
    original = runner.read_json
    monkeypatch.setattr(runner, "read_json", lambda value: mutated if value == runner.CONTRACT_PATH else original(value))
    with pytest.raises(ValueError, match="semantics drifted"):
        runner.contract()


def test_current_capacity_evidence_does_not_inherit_the_obsolete_august_28_gate(tmp_path: Path) -> None:
    runner = _runner()
    now = datetime(2026, 8, 22, 5, 0, tzinfo=UTC)
    receipt = tmp_path / "capacity.json"
    receipt.write_text(json.dumps(_receipt(now)), encoding="utf-8")
    assert runner.validate_capacity_evidence(receipt, now=now)["assertion"] == "capacity_available"


def test_capacity_evidence_requires_the_current_native_surface_and_freshness(tmp_path: Path) -> None:
    runner = _runner()
    now = datetime(2026, 8, 22, 5, 0, tzinfo=UTC)
    receipt = tmp_path / "capacity.json"
    receipt.write_text(json.dumps({**_receipt(now), "observation": {"surface": "text", "reference": "no"}}), encoding="utf-8")
    with pytest.raises(ValueError, match="native observation"):
        runner.validate_capacity_evidence(receipt, now=now)
    receipt.write_text(json.dumps(_receipt(now - timedelta(minutes=11))), encoding="utf-8")
    with pytest.raises(ValueError, match="not current"):
        runner.validate_capacity_evidence(receipt, now=now)


def test_prepare_is_offline_and_preserves_the_old_handoff_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    runner = _runner()
    schedule = [{"event": "planned", "fresh_dispatch": True, "sequence": 178}, {"event": "planned", "fresh_dispatch": True, "sequence": 179}]
    execution = {"closed_successor_binding_sha256": "a" * 64}

    class Previous:
        BINDING = "predecessor-binding.json"
        EXECUTION = "execution-contract.json"
        JOURNAL = "schedule.jsonl"

        @staticmethod
        def _roots(closed, source, work):
            return closed, source, work

        @staticmethod
        def _prepared_values(closed, source):
            return {}, schedule, execution

        @staticmethod
        def canonical(value):
            return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")

        @staticmethod
        def immutable_json(path, value):
            path.write_text(json.dumps(value, sort_keys=True) + "\n", encoding="utf-8")

        @staticmethod
        def _seal_schedule(work, value):
            (work / Previous.JOURNAL).write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in value), encoding="utf-8")

        @staticmethod
        def bind_closed_successor(closed):
            return {"closed": "immutable"}

    monkeypatch.setattr(runner, "_previous", lambda: Previous())
    monkeypatch.setattr(runner, "_expected_schedule", lambda previous, closed, source: (schedule, execution))
    result = runner.prepare(tmp_path / "closed", tmp_path / "source", tmp_path / "fresh")
    work = tmp_path / "fresh"
    assert result == {"provider_calls": 0, "cells": 2, "first_sequence": 178, "last_sequence": 179}
    assert (work / runner.CAPACITY_BINDING).is_file()
    assert json.loads((work / runner.CAPACITY_BINDING).read_text(encoding="utf-8"))["supersession"]["scope"].startswith("Replace only")
    assert not (work / "runs").exists()
    assert json.loads((work / Previous.JOURNAL).read_text(encoding="utf-8").splitlines()[0])["sequence"] == 178


def test_prepared_binding_rejects_provider_contract_and_runtime_drift(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    runner = _runner()
    schedule = [{"event": "planned", "fresh_dispatch": True, "sequence": 178}]
    execution = {"closed_successor_binding_sha256": "a" * 64}

    class Previous:
        BINDING = "predecessor-binding.json"
        EXECUTION = "execution-contract.json"
        JOURNAL = "schedule.jsonl"
        EXECUTOR_BINDING = "executor-binding.json"

        @staticmethod
        def _roots(closed, source, work):
            return closed, source, work

        @staticmethod
        def canonical(value):
            return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")

        @staticmethod
        def immutable_json(path, value):
            path.write_text(json.dumps(value, sort_keys=True) + "\n", encoding="utf-8")

        @staticmethod
        def _seal_schedule(work, value):
            (work / Previous.JOURNAL).write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in value), encoding="utf-8")

        @staticmethod
        def _read_output_journal(path):
            return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]

        @staticmethod
        def read_json(path):
            return json.loads(path.read_text(encoding="utf-8"))

        @staticmethod
        def bind_closed_successor(closed):
            return {"closed": "immutable"}

    monkeypatch.setattr(runner, "_previous", lambda: Previous())
    monkeypatch.setattr(runner, "_expected_schedule", lambda previous, closed, source: (schedule, execution))
    work = tmp_path / "fresh"
    runner.prepare(tmp_path / "closed", tmp_path / "source", work)
    runner._verify_prepared(tmp_path / "closed", tmp_path / "source", work)
    binding = json.loads((work / runner.CAPACITY_BINDING).read_text(encoding="utf-8"))
    binding["provider"]["model"] = "gpt-5.6-luna"
    (work / runner.CAPACITY_BINDING).write_text(json.dumps(binding), encoding="utf-8")
    with pytest.raises(ValueError, match="binding drifted"):
        runner._verify_prepared(tmp_path / "closed", tmp_path / "source", work)
    binding["provider"] = runner.contract()["provider"]
    (work / runner.CAPACITY_BINDING).write_text(json.dumps(binding), encoding="utf-8")
    monkeypatch.setattr(runner, "_runtime_commitment", lambda: {"files": [], "sha256": "f" * 64})
    with pytest.raises(ValueError, match="binding drifted"):
        runner._verify_prepared(tmp_path / "closed", tmp_path / "source", work)


def test_authorization_binds_the_old_33_file_executor_but_stays_non_executable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    runner = _runner()
    now = datetime(2026, 8, 22, 5, 0, tzinfo=UTC)
    work = tmp_path / "work"
    work.mkdir()
    receipt = tmp_path / "capacity.json"
    receipt.write_text(json.dumps(_receipt(now)), encoding="utf-8")

    class Previous:
        EXECUTOR_BINDING = "executor-binding.json"
        JOURNAL = "schedule.jsonl"

        @staticmethod
        def validate_executor_binding(*args):
            return {"runtime": {"files": [{}] * 33}}

    (work / Previous.EXECUTOR_BINDING).write_text("{}\n", encoding="utf-8")
    (work / Previous.JOURNAL).write_text("{}\n", encoding="utf-8")
    (work / runner.CAPACITY_BINDING).write_text("{}\n", encoding="utf-8")
    monkeypatch.setattr(runner, "_verify_prepared", lambda *args, **kwargs: (Previous(), [{"sequence": 178}], {}))
    result = runner.authorize(tmp_path / "closed", tmp_path / "source", work, receipt, now=now)
    authorization = json.loads((work / runner.AUTHORIZATION).read_text(encoding="utf-8"))
    assert result["provider_calls"] == 0
    assert result["executor_runtime_files"] == 33
    assert authorization["executable"] is False
    assert authorization["capacity_reset_binding_sha256"] == hashlib.sha256((work / runner.CAPACITY_BINDING).read_bytes()).hexdigest()
    assert authorization["capacity_evidence_sha256"] == hashlib.sha256((work / runner.CAPACITY_PREFLIGHT).read_bytes()).hexdigest()


def test_v2_seals_the_v1_executor_core_without_reopening_the_old_handoff(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    runner = _runner()
    work = tmp_path / "work"
    work.mkdir()

    class Previous:
        EXECUTOR_BINDING = "executor-binding.json"

        @staticmethod
        def bind_executor(*args):
            return {"runtime": {"files": [{}] * 33}}

        @staticmethod
        def immutable_json(path, value):
            path.write_text(json.dumps(value) + "\n", encoding="utf-8")

        @staticmethod
        def validate_executor_binding(*args):
            return {"runtime": {"files": [{}] * 33}}

    monkeypatch.setattr(runner, "_verify_prepared", lambda *args, **kwargs: (Previous(), [], {}))
    result = runner.seal_executor_binding(tmp_path / "executor", tmp_path / "launcher", tmp_path / "closed", tmp_path / "source", work)
    assert len(result["runtime"]["files"]) == 33
    assert (work / Previous.EXECUTOR_BINDING).is_file()
