from __future__ import annotations

import importlib.util
import json
import sys
import threading
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "evaluation-results" / "hbq-multisample-repeatability-v1-remainder-capacity-reset-executor-v3"


def _runner():
    spec = importlib.util.spec_from_file_location("capacity_reset_executor_v3", PACKAGE / "executor.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_contract_is_exact_and_v2_projection_matches_the_pushed_commit() -> None:
    runner = _runner()
    assert runner.contract()["base_v2_commit"] == "25783345f0bb18cf41cc641cd9aae90ab18ed25d"
    assert runner._v2_projection()["commit"] == runner.contract()["base_v2_commit"]


def test_contract_rejects_provider_capacity_and_execution_drift(monkeypatch: pytest.MonkeyPatch) -> None:
    runner = _runner()
    mutated = json.loads(runner.CONTRACT.read_text(encoding="utf-8"))
    mutated["provider"]["model"] = "gpt-5.6-luna"
    original = runner.read_json
    monkeypatch.setattr(runner, "read_json", lambda path: mutated if path == runner.CONTRACT else original(path))
    with pytest.raises(ValueError, match="semantics drifted"):
        runner.contract()


def test_base_rejects_missing_pushed_v2_predecessor_validator(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    runner = _runner()

    class V2:
        @staticmethod
        def _verify_prepared(*args, **kwargs):
            return None, [{"sequence": 178}], {}

        @staticmethod
        def _previous():
            return object()

        @staticmethod
        def canonical(value):
            return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")

    with pytest.raises(ValueError, match="validator API drifted"):
        runner._base(V2(), tmp_path / "closed", tmp_path / "source", tmp_path / "v2")


def test_exclusive_claim_allows_only_one_concurrent_epoch(tmp_path: Path) -> None:
    runner = _runner()
    source = tmp_path / "source"
    work = tmp_path / "work"
    source.mkdir(); work.mkdir()
    (source / "frozen-run-contract.json").write_text("{}\n", encoding="utf-8")
    barrier = threading.Barrier(2)
    results: list[str] = []

    def attempt() -> None:
        barrier.wait()
        try:
            runner._acquire_claim(work, source)
            results.append("claimed")
        except ValueError:
            results.append("blocked")

    threads = [threading.Thread(target=attempt), threading.Thread(target=attempt)]
    for thread in threads: thread.start()
    for thread in threads: thread.join()
    assert sorted(results) == ["blocked", "claimed"]
    assert (work / runner.CLAIM).is_file()


def test_unresolved_intent_stops_without_resend(tmp_path: Path) -> None:
    runner = _runner()
    work = tmp_path / "work"
    work.mkdir()
    event = {"sequence": 178}
    (work / runner.JOURNAL).write_text(json.dumps({"event": "capacity-checked", "sequence": 178, "capacity_proof_sha256": "a" * 64}) + "\n" + json.dumps({"event": "attempt-intent", "sequence": 178, "capacity_proof_sha256": "a" * 64}) + "\n", encoding="utf-8")

    class Previous:
        @staticmethod
        def _binding_path(work, event):
            return work / "runs" / "result.json"

    with pytest.raises(ValueError, match="Unresolved"):
        runner._completed(work, [event], Previous())


def test_completed_prefix_requires_its_persisted_capacity_proof(tmp_path: Path) -> None:
    runner = _runner()
    work = tmp_path / "work"
    work.mkdir()
    proof = "a" * 64
    rows = [
        {"event": "capacity-checked", "sequence": 178, "capacity_proof_sha256": proof},
        {"event": "attempt-intent", "sequence": 178, "capacity_proof_sha256": proof},
        {"event": "completed", "sequence": 178, "capacity_proof_sha256": proof, "output_sha256": "b" * 64},
    ]
    (work / runner.JOURNAL).write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")

    class Previous:
        @staticmethod
        def _binding_path(work, event):
            return work / "runs" / "result.json"

    with pytest.raises(ValueError, match="append-only"):
        runner._completed(work, [{"sequence": 178}], Previous())


def test_remote_dispatch_requires_explicit_review_gate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    runner = _runner()
    work = tmp_path / "work"
    work.mkdir()

    class V2:
        pass

    class Previous:
        @staticmethod
        def _binding_path(work, event):
            return work / "runs" / "result.json"

    monkeypatch.setattr(runner, "_verify", lambda *args: (V2(), Previous(), [{"sequence": 178}], {"lineage_sessions": {}}))
    with pytest.raises(ValueError, match="allow-remote"):
        runner.execute_one(tmp_path / "closed", tmp_path / "source", tmp_path / "v2", work, tmp_path / "capacity.json")


def test_crash_after_intent_preserves_claim_for_offline_adjudication(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    runner = _runner()
    source, work = tmp_path / "source", tmp_path / "work"
    source.mkdir(); work.mkdir()
    (source / "frozen-run-contract.json").write_text("{}\n", encoding="utf-8")

    class V2:
        @staticmethod
        def validate_capacity_evidence(*args, **kwargs):
            return {"observed_at": "2026-08-22T00:00:00+00:00"}

    class Previous:
        @staticmethod
        def _binding_path(work, event):
            return work / "runs" / "result.json"

        @staticmethod
        def read_json(path):
            return {}

        @staticmethod
        def _revalidate_predecessor_event(*args):
            raise RuntimeError("simulated dispatch precondition failure")

    evidence = tmp_path / "capacity.json"
    evidence.write_text("{}\n", encoding="utf-8")
    monkeypatch.setattr(runner, "_verify", lambda *args: (V2(), Previous(), [{"sequence": 178}], {"lineage_sessions": {}}))
    with pytest.raises(RuntimeError, match="simulated"):
        runner.execute_one(tmp_path / "closed", source, tmp_path / "v2", work, evidence, allow_remote=True)
    assert (work / runner.CLAIM).is_file()
    assert [json.loads(line)["event"] for line in (work / runner.JOURNAL).read_text(encoding="utf-8").splitlines()] == ["capacity-checked", "attempt-intent"]


def test_prepare_is_offline_and_writes_the_full_153_cell_schedule(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    runner = _runner()
    schedule = [{"event": "planned", "sequence": sequence} for sequence in range(178, 331)]

    class V2:
        CAPACITY_BINDING = "capacity-reset-binding.json"

        @staticmethod
        def canonical(value):
            return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")

        @staticmethod
        def _previous():
            class Previous:
                EXECUTOR_BINDING = "executor-binding.json"
                EXECUTION = "remainder-execution-contract.json"
            return Previous()

    v2work = tmp_path / "v2"
    v2work.mkdir()
    for name in ("capacity-reset-binding.json", "executor-binding.json", "remainder-execution-contract.json"):
        (v2work / name).write_text("{}\n", encoding="utf-8")
    monkeypatch.setattr(runner, "_load_v2", lambda: V2())
    monkeypatch.setattr(runner, "_base", lambda *args: (schedule, {"lineage_sessions": {}}))
    monkeypatch.setattr(runner, "_v2_projection", lambda: {"commit": "25783345f0bb18cf41cc641cd9aae90ab18ed25d", "files": [], "sha256": "a" * 64})
    result = runner.prepare(tmp_path / "closed", tmp_path / "source", v2work, tmp_path / "work")
    assert result == {"provider_calls": 0, "cells": 153, "first_sequence": 178, "last_sequence": 330}
    assert len((tmp_path / "work" / runner.SCHEDULE).read_text(encoding="utf-8").splitlines()) == 153
    assert not (tmp_path / "work" / "runs").exists()
