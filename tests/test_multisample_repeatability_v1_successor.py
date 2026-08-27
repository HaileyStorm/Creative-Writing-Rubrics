from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "evaluation-results" / "hbq-multisample-repeatability-v1-successor-v1"


def _module(name: str):
    previous, sys.modules["study"] = sys.modules.get("study"), None  # type: ignore[assignment]
    sys.modules.pop("study", None)
    sys.path.insert(0, str(PACKAGE))
    try:
        spec = importlib.util.spec_from_file_location(name, PACKAGE / f"{name}.py")
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.remove(str(PACKAGE))
        sys.modules.pop("study", None)
        if previous is not None:
            sys.modules["study"] = previous


def _schedule() -> list[dict[str, object]]:
    return [{"item_id": f"story-{index}", "arm_id": "hbq_short_story_batch32", "repetition": 1, "position": 1} for index in range(330)]


def _frozen(path: Path) -> None:
    path.write_text(json.dumps({"schedule": _schedule(), "contract": {"provider": {"model": "gpt-5.6-sol", "reasoning": "high"}}}), encoding="utf-8")


def _external_test_work(monkeypatch: pytest.MonkeyPatch, runner, tmp_path: Path) -> None:
    monkeypatch.setattr(runner, "REPO", tmp_path / "unrelated-repository")
    monkeypatch.setattr(runner, "_runtime_projection", lambda frozen: {"fixture": "stable"})


def test_quote_projection_is_exact_or_one_outer_curly_pair_only() -> None:
    runner = _module("run_successor")
    source = "One exact sentence."
    assert runner._project_quote("One exact sentence.", source) == ("One exact sentence.", "exact")
    assert runner._project_quote("“One exact sentence.”", source) == ("One exact sentence.", "outer_curly_pair_removed")
    for invalid in (" One exact sentence.", '"One exact sentence."', "“One exact sentence.” ", "“One  exact sentence.”"):
        with pytest.raises(ValueError):
            runner._project_quote(invalid, source)


def test_manifest_serialization_is_explicit_and_tamper_sensitive() -> None:
    study = _module("study")
    rows = [{"path": "a", "bytes": 1, "sha256": "a" * 64}, {"path": "b", "bytes": 2, "sha256": "b" * 64}]
    expected = hashlib.sha256(b"a\t1\t" + b"a" * 64 + b"\nb\t2\t" + b"b" * 64 + b"\n").hexdigest()
    assert study._manifest_sha256(rows) == expected
    assert study._manifest_sha256([{**rows[0], "bytes": 3}, rows[1]]) != expected


def test_predecessor_binding_fails_closed_on_a_tampered_full_manifest(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    study = _module("study")
    monkeypatch.setattr(study, "_manifest", lambda root: [])
    with pytest.raises(ValueError, match="Full predecessor manifest drifted"):
        study.bind_predecessor(tmp_path)


def test_successor_geometry_starts_at_77_and_never_inherits_a_rerun(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    runner = _module("run_successor")
    predecessor = tmp_path / "predecessor"
    predecessor.mkdir()
    _frozen(predecessor / "frozen-run-contract.json")
    bound = {"accepted_prefix": {"count": 76}, "sessions": {"count": 146}, "root_manifest": {"file_count": 801}}
    monkeypatch.setattr(runner, "bind_predecessor", lambda root: bound)
    _external_test_work(monkeypatch, runner, tmp_path)
    result = runner.prepare(predecessor, tmp_path / "successor")
    records = runner._read_journal(result["journal"])
    assert len(records) == 254
    assert records[0]["sequence"] == 77
    assert records[-1]["sequence"] == 330
    assert not (tmp_path / "successor" / "runs").exists()


def test_operator_work_root_cannot_overlap_predecessor_or_repository(tmp_path: Path) -> None:
    runner = _module("run_successor")
    predecessor = tmp_path / "predecessor"
    predecessor.mkdir()
    for work in (predecessor, predecessor / "child", ROOT / ".successor-private-output"):
        with pytest.raises(ValueError, match="must not overlap|outside the repository"):
            runner._operator_work_root(predecessor, work)


def test_runtime_projection_drift_is_rejected_after_prepare(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    runner = _module("run_successor")
    predecessor = tmp_path / "predecessor"
    predecessor.mkdir()
    _frozen(predecessor / "frozen-run-contract.json")
    bound = {"accepted_prefix": {"count": 76}, "sessions": {"count": 146}, "root_manifest": {"file_count": 801}}
    monkeypatch.setattr(runner, "bind_predecessor", lambda root: bound)
    _external_test_work(monkeypatch, runner, tmp_path)
    work = tmp_path / "successor"
    runner.prepare(predecessor, work)
    frozen = runner.read_json(predecessor / "frozen-run-contract.json")
    monkeypatch.setattr(runner, "_runtime_projection", lambda value: {"drifted": True})
    with pytest.raises(ValueError, match="runtime projection drifted"):
        runner._revalidate_runtime(work, frozen)


def test_execute_revalidates_runtime_before_each_dispatch_and_stops_on_drift(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    runner = _module("run_successor")
    predecessor, work = tmp_path / "predecessor", tmp_path / "successor"
    predecessor.mkdir()
    _frozen(predecessor / "frozen-run-contract.json")
    frozen = runner.read_json(predecessor / "frozen-run-contract.json")
    journal = work / runner.JOURNAL
    monkeypatch.setattr(runner, "_operator_work_root", lambda predecessor, work: (predecessor, work))
    monkeypatch.setattr(runner, "prepare", lambda predecessor, work: {"completed": 0, "journal": journal})
    monkeypatch.setattr(runner, "_successor_plans", lambda frozen: [{"sequence": 77, "item_id": "story", "arm_id": "hbq_short_story_batch32", "repetition": 1}])
    monkeypatch.setattr(runner, "_v1_runner", lambda: object())
    calls: list[str] = []
    monkeypatch.setattr(runner, "_revalidate_runtime", lambda work, frozen: calls.append("runtime"))
    monkeypatch.setattr(runner, "_revalidate_predecessor_event", lambda predecessor, frozen, event: calls.append("predecessor"))
    monkeypatch.setattr(runner, "_validate_normalization", lambda *args: None)
    target = work / "run.json"
    monkeypatch.setattr(runner, "_run_event", lambda *args: (calls.append("dispatch"), target.parent.mkdir(parents=True, exist_ok=True), target.write_text("{}", encoding="utf-8"), target)[-1])
    monkeypatch.setattr(runner, "_validate_global_sessions", lambda *args: None)
    result = runner.execute(predecessor, work, allow_remote=True)
    assert result == {"provider_calls": 1, "cells": 1}
    assert calls == ["runtime", "runtime", "predecessor", "dispatch"]

    calls.clear()
    monkeypatch.setattr(runner, "_revalidate_runtime", lambda work, frozen: (_ for _ in ()).throw(ValueError("runtime drift")))
    monkeypatch.setattr(runner, "_run_event", lambda *args: pytest.fail("provider dispatched after runtime drift"))
    with pytest.raises(ValueError, match="runtime drift"):
        runner.execute(predecessor, work, allow_remote=True)
    assert calls == []


def test_successor_threads_before_provider_attempt_to_run_judge(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    runner = _module("run_successor")
    predecessor, work = tmp_path / "predecessor", tmp_path / "successor"
    folder = predecessor / "inputs" / "story"
    folder.mkdir(parents=True)
    (folder / "source.md").write_text("source", encoding="utf-8")
    (folder / "prompt.md").write_text("prompt", encoding="utf-8")
    event = {"sequence": 77, "item_id": "story", "arm_id": "comparison", "repetition": 1}
    frozen = {
        "contract": {
            "provider": {"model": "gpt-5.6-sol", "reasoning": "high"},
            "arms": [{"arm_id": "comparison", "kind": "comparison", "bundle_id": "prose.scene", "batch_size": 1, "batch_attempts": 2}],
        }
    }
    captured: dict[str, object] = {}
    hook = lambda context: None
    monkeypatch.setattr(runner, "run_judge", lambda **kwargs: captured.update(kwargs))

    target = runner._run_event(object(), event, frozen, predecessor, work, 30.0, before_provider_attempt=hook)
    assert target == work / "runs" / "story" / "comparison" / "run-01" / "run.json"
    assert captured["before_provider_attempt"] is hook


def test_recovered_prefix_session_collision_stops_before_new_dispatch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    runner = _module("run_successor")
    predecessor, work = tmp_path / "predecessor", tmp_path / "successor"
    predecessor.mkdir()
    _frozen(predecessor / "frozen-run-contract.json")
    first = {"sequence": 77, "item_id": "first", "arm_id": "hbq_short_story_batch32", "repetition": 1}
    second = {"sequence": 78, "item_id": "second", "arm_id": "hbq_short_story_batch32", "repetition": 1}
    source = predecessor / "inputs" / "first" / "source.md"
    source.parent.mkdir(parents=True)
    source.write_text("fixture", encoding="utf-8")
    monkeypatch.setattr(runner, "_operator_work_root", lambda predecessor, work: (predecessor, work))
    monkeypatch.setattr(runner, "prepare", lambda predecessor, work: {"completed": 1, "journal": work / runner.JOURNAL})
    monkeypatch.setattr(runner, "_successor_plans", lambda frozen: [first, second])
    monkeypatch.setattr(runner, "_revalidate_runtime", lambda *args: None)
    monkeypatch.setattr(runner, "_revalidate_predecessor_event", lambda *args: None)
    monkeypatch.setattr(runner, "_validate_normalization", lambda *args: None)
    monkeypatch.setattr(runner, "_v1_runner", lambda: object())
    monkeypatch.setattr(runner, "_validate_global_sessions", lambda *args: (_ for _ in ()).throw(ValueError("recovered session collision")))
    monkeypatch.setattr(runner, "_run_event", lambda *args: pytest.fail("provider dispatched after recovered collision"))
    with pytest.raises(ValueError, match="recovered session collision"):
        runner.execute(predecessor, work, allow_remote=True)


def test_predecessor_event_input_drift_fails_before_dispatch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    runner = _module("run_successor")
    predecessor = tmp_path / "predecessor"
    predecessor.mkdir()
    source = predecessor / "inputs" / "story" / "source.md"
    source.parent.mkdir(parents=True)
    source.write_text("source", encoding="utf-8")
    prompt, task = source.with_name("prompt.md"), source.with_name("task-contract.json")
    prompt.write_text("prompt", encoding="utf-8")
    task.write_text("{}", encoding="utf-8")
    frozen = {"samples": [{"item_id": "story", "inputs": {name: {"bytes": path.stat().st_size, "sha256": runner.sha(path)} for name, path in (("source.md", source), ("prompt.md", prompt), ("task-contract.json", task))}}]}
    frozen_path = predecessor / "frozen-run-contract.json"
    frozen_path.write_text(json.dumps(frozen), encoding="utf-8")
    monkeypatch.setitem(runner.PREDECESSOR, "frozen_contract_sha256", runner.sha(frozen_path))
    event = {"item_id": "story"}
    runner._revalidate_predecessor_event(predecessor, frozen, event)
    source.write_text("changed", encoding="utf-8")
    with pytest.raises(ValueError, match="source, prompt, or task contract drifted"):
        runner._revalidate_predecessor_event(predecessor, frozen, event)


def test_runtime_rejects_untracked_or_dirty_successor_projection(monkeypatch: pytest.MonkeyPatch) -> None:
    runner = _module("run_successor")
    import subprocess

    monkeypatch.setattr(runner.subprocess, "check_output", lambda *args, **kwargs: (_ for _ in ()).throw(subprocess.CalledProcessError(1, args[0])))
    with pytest.raises(ValueError, match="not tracked"):
        runner._runtime_file(PACKAGE / "run_successor.py")

    def git(command, **kwargs):
        if command[1:3] in (["rev-parse", "HEAD"], ["rev-parse", "@{u}"]):
            return "a" * 40 + "\n"
        if command[1:3] == ["status", "--porcelain"]:
            return " M evaluation-results/hbq-multisample-repeatability-v1-successor-v1/run_successor.py\n"
        raise AssertionError(command)

    monkeypatch.setattr(runner.subprocess, "check_output", git)
    with pytest.raises(ValueError, match="clean checkout"):
        runner._runtime_projection({"contract": {"arms": []}})


def test_dry_run_makes_zero_calls_and_freezes_restart_boundary(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    runner = _module("run_successor")
    predecessor = tmp_path / "predecessor"
    predecessor.mkdir()
    _frozen(predecessor / "frozen-run-contract.json")
    bound = {"accepted_prefix": {"count": 76}, "sessions": {"count": 146}, "root_manifest": {"file_count": 801}}
    monkeypatch.setattr(runner, "bind_predecessor", lambda root: bound)
    _external_test_work(monkeypatch, runner, tmp_path)
    monkeypatch.setattr(runner, "_run_event", lambda *args, **kwargs: pytest.fail("dry-run called provider route"))
    work = tmp_path / "successor"
    assert runner.execute(predecessor, work, dry_run=True) == {"provider_calls": 0, "cells": 254, "first_sequence": 77}
    execution = work / runner.EXECUTION
    execution.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="Immutable successor artifact drifted"):
        runner.prepare(predecessor, work)


def test_session_collision_is_rejected_before_completion(tmp_path: Path) -> None:
    runner = _module("run_successor")
    output = tmp_path / "run"
    output.mkdir()
    (output / "response.json").write_text(json.dumps({"provider": {"reported": {"session_id": "same"}}}), encoding="utf-8")
    (output / "attempts").mkdir()
    (output / "attempts" / "rejected-0001.json").write_text(json.dumps({"response": {"provider": {"reported": {"session_id": "same"}}}}), encoding="utf-8")
    with pytest.raises(ValueError, match="unique provider session"):
        runner._session_ids_in_output(output)


def test_normalization_restart_requires_exact_raw_and_audit_artifacts(tmp_path: Path) -> None:
    runner = _module("run_successor")
    output = tmp_path / "run"
    output.mkdir()
    raw = {"provider": {"reported": {"session_id": "new"}}, "result_sha256": "placeholder"}
    result = {"evidence": [{"quote": "“One exact sentence.”"}]}
    (output / "pass.json").write_text("{}", encoding="utf-8")
    (output / "response.json").write_text(json.dumps(raw), encoding="utf-8")
    (output / "result.json").write_text(json.dumps(result), encoding="utf-8")

    class Semantic:
        def _semantic_native(self, value, arm, source):
            if value["evidence"][0]["quote"] not in source:
                raise ValueError("ungrounded")

    assert runner._semantic_native(Semantic(), result, "holistic_anchored", "One exact sentence.", output)["evidence"][0]["quote"] == "One exact sentence."
    assert runner._semantic_native(Semantic(), result, "holistic_anchored", "One exact sentence.", output)["evidence"][0]["quote"] == "One exact sentence."
    (output / "normalization-audit.json").write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="Normalization projection or audit drifted"):
        runner._semantic_native(Semantic(), result, "holistic_anchored", "One exact sentence.", output)
    (output / "normalization-audit.json").unlink()
    with pytest.raises(ValueError, match="missing raw or projected artifacts"):
        runner._semantic_native(Semantic(), result, "holistic_anchored", "One exact sentence.", output)
    (output / "raw-response.json").unlink()
    (output / "raw-result.json").unlink()
    (output / "normalization-marker.json").unlink()
    with pytest.raises(ValueError, match="missing raw or projected artifacts"):
        runner._semantic_native(Semantic(), result, "holistic_anchored", "One exact sentence.", output)


def test_v1_bytes_are_not_mutated_by_successor_prepare(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    runner = _module("run_successor")
    original = ROOT / "evaluation-results" / "hbq-multisample-repeatability-v1" / "run_study.py"
    before = hashlib.sha256(original.read_bytes()).hexdigest()
    predecessor = tmp_path / "predecessor"
    predecessor.mkdir()
    _frozen(predecessor / "frozen-run-contract.json")
    monkeypatch.setattr(runner, "bind_predecessor", lambda root: {"accepted_prefix": {"count": 76}, "sessions": {"count": 146}, "root_manifest": {"file_count": 801}})
    _external_test_work(monkeypatch, runner, tmp_path)
    runner.prepare(predecessor, tmp_path / "successor")
    assert hashlib.sha256(original.read_bytes()).hexdigest() == before


def test_combined_adapter_rejects_an_incomplete_successor_fixture(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    analysis = _module("analyze_successor")
    predecessor = tmp_path / "predecessor"
    predecessor.mkdir()
    _frozen(predecessor / "frozen-run-contract.json")
    binding = {"accepted_prefix": {"count": 76}, "sessions": {"count": 146}, "root_manifest": {"file_count": 801}}
    monkeypatch.setattr(analysis, "bind_predecessor", lambda root: binding)
    monkeypatch.setattr(analysis, "predecessor_session_ids", lambda root: ["old"])
    work = tmp_path / "successor"
    work.mkdir()
    (work / analysis.BINDING).write_text(json.dumps(binding), encoding="utf-8")
    (work / analysis.EXECUTION).write_text(json.dumps({"predecessor_binding_sha256": hashlib.sha256(analysis.canonical(binding)).hexdigest()}), encoding="utf-8")
    with pytest.raises(ValueError, match="incomplete"):
        analysis.validate_combined(predecessor, work)


def test_combined_adapter_accepts_a_complete_330_cell_lineage_fixture(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    analysis = _module("analyze_successor")
    predecessor = tmp_path / "predecessor"
    predecessor.mkdir()
    _frozen(predecessor / "frozen-run-contract.json")
    binding = {"accepted_prefix": {"count": 76}, "sessions": {"count": 146}, "root_manifest": {"file_count": 801}}
    monkeypatch.setattr(analysis, "bind_predecessor", lambda root: binding)
    monkeypatch.setattr(analysis, "predecessor_session_ids", lambda root: [f"old-{index}" for index in range(146)])
    work = tmp_path / "successor"
    work.mkdir()
    (work / analysis.BINDING).write_text(json.dumps(binding), encoding="utf-8")
    (work / analysis.EXECUTION).write_text(json.dumps({"predecessor_binding_sha256": hashlib.sha256(analysis.canonical(binding)).hexdigest()}), encoding="utf-8")
    frozen = analysis.read_json(predecessor / "frozen-run-contract.json")
    events = analysis.plans(frozen)[76:]
    records = list(events)
    for event in events:
        source = predecessor / "inputs" / str(event["item_id"]) / "source.md"
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text("fixture source", encoding="utf-8")
        target = analysis._binding_path(work, event)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("{}", encoding="utf-8")
        (target.parent / "response.json").write_text(json.dumps({"provider": {"reported": {"session_id": f"new-{event['sequence']}"}}}), encoding="utf-8")
        records.append({**event, "event": "completed", "run_binding_sha256": analysis.sha(target)})
    (work / analysis.JOURNAL).write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in records), encoding="utf-8")
    value = analysis.validate_combined(predecessor, work)
    assert value["combined"]["count"] == 330
    assert value["successor"] == {"count": 254, "first_sequence": 77, "last_sequence": 330, "session_count": 254}
    monkeypatch.setattr(analysis, "predecessor_session_ids", lambda root: ["new-77"] + [f"old-{index}" for index in range(145)])
    with pytest.raises(ValueError, match="collides with predecessor"):
        analysis.validate_combined(predecessor, work)
    monkeypatch.setattr(analysis, "predecessor_session_ids", lambda root: [f"old-{index}" for index in range(146)])
    first_target = analysis._binding_path(work, events[0])
    first_target.write_text(json.dumps({"normalization_marker_sha256": "a" * 64}), encoding="utf-8")
    records[254]["run_binding_sha256"] = analysis.sha(first_target)
    (work / analysis.JOURNAL).write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in records), encoding="utf-8")
    monkeypatch.setattr(analysis, "_v1_runner", lambda: object())
    monkeypatch.setattr(analysis, "_validate_normalization", lambda *args: (_ for _ in ()).throw(ValueError("missing normalized sidecars")))
    with pytest.raises(ValueError, match="missing normalized sidecars"):
        analysis.validate_combined(predecessor, work)
