from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

import hbqrs.batch as batch_module
from hbqrs.batch import _status_html, run_longform_batch, validate_batch_manifest
from hbqrs.core import HBQError
from hbqrs.paths import bundles_path, registry_path


def _manifest(tmp_path: Path, policy: str) -> dict[str, object]:
    for name in ("one.txt", "two.txt"):
        (tmp_path / name).write_text("Chapter One\n\nA test scene.\n", encoding="utf-8")
    value: dict[str, object] = {
        "batch_version": 1,
        "batch_id": "test-batch",
        "routing_policy": policy,
        "defaults": {
            "provider": "codex",
            "model": "gpt-5.6-sol",
            "output_root": "outputs",
            "artifact_kind": "prose_fiction",
            "declared_scope": "manuscript",
            "completion_status": "work_in_progress",
            "batch_attempts": 5,
        },
        "jobs": [
            {"job_id": "one", "artifact": "one.txt"},
            {"job_id": "two", "artifact": "two.txt"},
        ],
    }
    if policy == "shared":
        value["shared_route_source_job_id"] = "one"
    return value


def _install_fake(monkeypatch: pytest.MonkeyPatch, calls: list[dict[str, object]]) -> None:
    def fake_runner(**kwargs):
        calls.append(kwargs)
        if kwargs["plan_only"]:
            output = Path(kwargs["output_dir"])
            if kwargs["resume"] and not (output / "plan.json").is_file():
                raise HBQError("Cannot resume a missing batch plan")
            output.mkdir(parents=True, exist_ok=True)
            bundle_id = kwargs.get("bundle_id") or "prose.novel"
            module_ids = list(
                kwargs.get("module_ids")
                or ["craft.narrative.characterization", "form.prose.novel"]
            )
            artifact_id = Path(kwargs["artifact_path"]).stem
            inputs = output / ".private" / "inputs"
            inputs.mkdir(parents=True, exist_ok=True)
            source = inputs / "artifact.txt"
            source.write_bytes(Path(kwargs["artifact_path"]).read_bytes())
            contexts = []
            for index, path in enumerate(kwargs["brief_paths"], start=1):
                copy = inputs / f"brief-{index:02d}.txt"
                copy.write_bytes(Path(path).read_bytes())
                contexts.append({
                    "path": f".private/inputs/{copy.name}", "bytes": copy.stat().st_size,
                    "sha256": hashlib.sha256(copy.read_bytes()).hexdigest(),
                })
            if kwargs["driving_prompt"]:
                copy = inputs / "driving-prompt.txt"
                copy.write_text(kwargs["driving_prompt"], encoding="utf-8")
                contexts.append({
                    "path": f".private/inputs/{copy.name}", "bytes": copy.stat().st_size,
                    "sha256": hashlib.sha256(copy.read_bytes()).hexdigest(),
                })
            route = {
                "artifact_profile": {
                    "artifact_kind": "prose_fiction", "declared_scope": "manuscript",
                    "completion_status": "work_in_progress", "unit_count": 1,
                    "source_sha256": "a" * 64,
                },
                "selected_bundle_id": bundle_id,
                "selected_module_ids": module_ids,
                "task_contract": {
                    "contract_version": 1,
                    "contract_id": f"route-{artifact_id}",
                    "artifact_id": artifact_id,
                    "context": {
                        "artifact_kind": "prose_fiction",
                        "declared_scope": "manuscript",
                        "completion_status": "work_in_progress",
                        "background": [],
                        "constraints": [],
                        "audience": [],
                    },
                    "preferences": [],
                    "priorities": [],
                    "weighted_goals": [],
                    "binding_requirements": [],
                },
                "sampling_plan": {
                    "coverage_mode": "complete",
                    "unit_ids": ["unit-0001-aaaaaaaaaaaa"],
                    "strata": [
                        {"name": "complete", "unit_ids": ["unit-0001-aaaaaaaaaaaa"]}
                    ],
                    "global_map_required": True,
                    "rationale": "Complete test coverage.",
                },
            }
            plan = {
                "artifact_id": artifact_id,
                "route": route,
                "source_artifact": {
                    "path": ".private/inputs/artifact.txt", "bytes": source.stat().st_size,
                    "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                },
                "context_artifacts": contexts,
                "local_bundle_plan": {
                    "global_bundle_id": bundle_id,
                    "local_bundle_id": bundle_id,
                    "local_bundle_mode": "fixture",
                },
            }
            (output / "plan.json").write_text(json.dumps(plan), encoding="utf-8")
            return {
                "status": "PLANNED", "selected_bundle_id": bundle_id,
                "selected_module_ids": module_ids, **plan,
            }
        return {"status": "COMPLETE"}

    monkeypatch.setattr("hbqrs.batch.run_longform_judge", fake_runner)


def _write_manifest(tmp_path: Path, value: dict[str, object]) -> Path:
    path = tmp_path / "batch.json"
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


def test_individual_policy_routes_each_job_without_confirmation(tmp_path: Path, monkeypatch) -> None:
    calls: list[dict[str, object]] = []
    _install_fake(monkeypatch, calls)
    state = run_longform_batch(
        _write_manifest(tmp_path, _manifest(tmp_path, "individual")),
        registry="registry.jsonl", bundles="bundles.jsonl", allow_remote=True,
    )
    assert state["phase"] == "complete"
    assert len(calls) == 2
    assert all(call["plan_only"] is False and call["bundle_id"] is None for call in calls)
    assert all(call["upgrade_legacy_normalization"] is False for call in calls)
    status = (tmp_path / "outputs" / "batch-status.html").read_text(encoding="utf-8")
    assert "one.txt" not in status
    assert '<meta http-equiv="refresh"' not in status
    assert 'id="hbqrs-auto-refresh"' in status
    assert "window.location.reload()" in status
    assert "Last updated:" in status
    persisted = json.loads((tmp_path / "outputs" / "batch.json").read_text(encoding="utf-8"))
    assert persisted["updated_at"] in status


def test_batch_status_page_is_pausable_accessible_and_static_without_scripting() -> None:
    status = _status_html(
        {
            "batch_id": "example-batch",
            "routing_policy": "individual",
            "updated_at": "2026-08-20T12:34:56+00:00",
            "jobs": [{"job_id": "one", "status": "RUNNING", "detail": "grading"}],
        }
    )
    assert '<meta http-equiv="refresh"' not in status
    assert 'type="checkbox" checked' in status
    assert "Automatic refresh is paused." in status
    assert 'aria-live="polite"' in status
    assert "input:focus-visible" in status
    assert "<noscript>" in status
    assert "window.location.reload()" in status
    assert '<time datetime="2026-08-20T12:34:56+00:00">' in status
    assert "<script src=" not in status


def test_shared_policy_freezes_designated_llm_route_for_all_jobs(tmp_path: Path, monkeypatch) -> None:
    calls: list[dict[str, object]] = []
    _install_fake(monkeypatch, calls)
    run_longform_batch(
        _write_manifest(tmp_path, _manifest(tmp_path, "shared")),
        registry=registry_path(), bundles=bundles_path(), allow_remote=True,
    )
    assert len(calls) == 5
    assert [call["plan_only"] for call in calls] == [True, True, True, False, False]
    assert [call["bundle_id"] for call in calls[1:]] == ["prose.novel"] * 4
    assert all(
        call["module_ids"] == ["craft.narrative.characterization", "form.prose.novel"]
        for call in calls[1:]
    )


def test_review_policy_plans_every_job_then_accepts_or_overrides(tmp_path: Path, monkeypatch) -> None:
    calls: list[dict[str, object]] = []
    _install_fake(monkeypatch, calls)
    manifest = _manifest(tmp_path, "review")
    path = _write_manifest(tmp_path, manifest)
    planned = run_longform_batch(
        path, registry=registry_path(), bundles=bundles_path(), allow_remote=True
    )
    assert planned["phase"] == "awaiting_review"
    assert len(calls) == 2 and all(call["plan_only"] for call in calls)

    manifest["jobs"][1]["approved_bundle_id"] = "prose.chapter"
    manifest["jobs"][1]["approved_module_ids"] = ["craft.narrative.characterization"]
    path.write_text(json.dumps(manifest), encoding="utf-8")
    accepted = run_longform_batch(
        path, registry=registry_path(), bundles=bundles_path(),
        allow_remote=True, accept_reviewed=True,
    )
    assert accepted["phase"] == "complete"
    assert [call["plan_only"] for call in calls] == [True, True, True, True, True, False, False]
    assert [call["bundle_id"] for call in calls[-2:]] == [None, "prose.chapter"]
    assert calls[-2]["output_dir"] == tmp_path / "outputs" / "plans" / "one"
    assert calls[-1]["output_dir"] == tmp_path / "outputs" / "approved-plans" / "two"
    assert calls[-2]["resume"] is True and calls[-1]["resume"] is True
    assert all(call["batch_attempts"] == 5 for call in calls)
    assert calls[4]["task_contract_path"] == (
        tmp_path / "outputs" / ".private" / "approved-plans" / "two" / "task-contract.json"
    )
    assert calls[4]["sampling_plan_override"] == {
        "coverage_mode": "complete",
        "unit_ids": ["unit-0001-aaaaaaaaaaaa"],
        "strata": [{"name": "complete", "unit_ids": ["unit-0001-aaaaaaaaaaaa"]}],
        "global_map_required": True,
        "rationale": "Complete test coverage.",
    }
    assert calls[-1]["task_contract_path"] == calls[4]["task_contract_path"]
    assert calls[-1]["sampling_plan_override"] == calls[4]["sampling_plan_override"]


def test_review_acceptance_rejects_an_incomplete_plan_set_before_grading(
    tmp_path: Path, monkeypatch
) -> None:
    calls: list[dict[str, object]] = []
    _install_fake(monkeypatch, calls)
    path = _write_manifest(tmp_path, _manifest(tmp_path, "review"))
    run_longform_batch(
        path, registry=registry_path(), bundles=bundles_path(), allow_remote=True
    )
    (tmp_path / "outputs" / "plans" / "two" / "plan.json").unlink()

    with pytest.raises(HBQError, match="missing batch plan"):
        run_longform_batch(
            path, registry=registry_path(), bundles=bundles_path(),
            allow_remote=True, accept_reviewed=True,
        )
    assert all(call["plan_only"] is True for call in calls)


def test_batch_manifest_is_strict_and_shared_source_must_exist(tmp_path: Path) -> None:
    value = _manifest(tmp_path, "individual")
    value["surprise"] = True
    with pytest.raises(HBQError, match="strict schema"):
        validate_batch_manifest(value)
    shared = _manifest(tmp_path, "shared")
    shared["shared_route_source_job_id"] = "missing"
    with pytest.raises(HBQError, match="must name a job"):
        validate_batch_manifest(shared)
    single_html = _manifest(tmp_path, "individual")
    single_html["defaults"]["html_report"] = True
    single_html["jobs"][0]["workflow"] = "single"
    with pytest.raises(HBQError, match="long-form HTML"):
        validate_batch_manifest(single_html)


def test_batch_rejects_output_that_contains_its_manifest_or_an_unrelated_state(
    tmp_path: Path,
) -> None:
    overlap = _manifest(tmp_path, "individual")
    overlap["defaults"]["output_root"] = "."
    overlap_path = _write_manifest(tmp_path, overlap)
    with pytest.raises(HBQError, match="must not contain the manifest"):
        run_longform_batch(
            overlap_path, registry=registry_path(), bundles=bundles_path(), allow_remote=True
        )

    value = _manifest(tmp_path, "individual")
    path = _write_manifest(tmp_path, value)
    output = tmp_path / "outputs"
    output.mkdir()
    (output / "batch.json").write_text(
        json.dumps(
            {
                "format_version": 1,
                "batch_id": "some-other-batch",
                "routing_policy": "individual",
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(HBQError, match="does not belong"):
        run_longform_batch(
            path, registry=registry_path(), bundles=bundles_path(),
            allow_remote=True, resume=True,
        )


def test_batch_binds_and_propagates_legacy_normalization_upgrade(
    tmp_path: Path, monkeypatch
) -> None:
    calls: list[dict[str, object]] = []
    _install_fake(monkeypatch, calls)
    manifest = _manifest(tmp_path, "individual")
    path = _write_manifest(tmp_path, manifest)
    run_longform_batch(
        path, registry="registry.jsonl", bundles="bundles.jsonl", allow_remote=True,
    )
    state_path = tmp_path / "outputs" / "batch.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["configuration"]["upgrade_legacy_normalization"]["defaults"] is False
    assert all(
        value is False
        for value in state["configuration"]["upgrade_legacy_normalization"]["jobs"].values()
    )

    manifest["defaults"]["upgrade_legacy_normalization"] = True
    path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(HBQError, match="upgrade_legacy_normalization policy changed"):
        run_longform_batch(
            path, registry="registry.jsonl", bundles="bundles.jsonl", allow_remote=True, resume=True,
        )

    legacy_root = tmp_path / "legacy-outputs"
    legacy_root.mkdir()
    (legacy_root / "batch.json").write_text(
        json.dumps({"format_version": 1, "batch_id": "test-batch", "routing_policy": "individual"}),
        encoding="utf-8",
    )
    manifest["defaults"]["output_root"] = "legacy-outputs"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    calls.clear()
    state = run_longform_batch(
        path, registry="registry.jsonl", bundles="bundles.jsonl", allow_remote=True, resume=True,
    )
    assert state["configuration"]["upgrade_legacy_normalization"]["defaults"] is True
    assert all(call["upgrade_legacy_normalization"] is True for call in calls)

def test_batch_renders_html_for_a_valid_control_state(tmp_path: Path, monkeypatch) -> None:
    calls: list[dict[str, object]] = []

    def fake_runner(**kwargs):
        calls.append(kwargs)
        output = Path(kwargs["output_dir"])
        output.mkdir(parents=True, exist_ok=True)
        (output / "report.json").write_text("{}", encoding="utf-8")
        return {"status": "VALID"}

    monkeypatch.setattr("hbqrs.batch.run_longform_judge", fake_runner)
    monkeypatch.setattr("hbqrs.batch.render_html_report", lambda report: "full")
    monkeypatch.setattr("hbqrs.batch.render_html_scorecard", lambda report: "card")
    manifest = _manifest(tmp_path, "individual")
    manifest["defaults"]["html_report"] = True
    run_longform_batch(
        _write_manifest(tmp_path, manifest),
        registry=registry_path(), bundles=bundles_path(), allow_remote=True,
    )
    for job_id in ("one", "two"):
        output = tmp_path / "outputs" / "jobs" / job_id
        assert (output / "report.html").read_text(encoding="utf-8") == "full"
        assert (output / "scorecard.html").read_text(encoding="utf-8") == "card"


def test_batch_can_mix_longform_and_single_scope_without_duplicate_single_scoring(
    tmp_path: Path, monkeypatch
) -> None:
    longform_calls: list[dict[str, object]] = []
    single_calls: list[dict[str, object]] = []
    _install_fake(monkeypatch, longform_calls)
    monkeypatch.setattr(
        "hbqrs.batch._longform_scope_compatibility_proof",
        lambda **kwargs: {
            "mode": "longform_prevalidated_route",
            "artifact_id": kwargs["artifact_id"], "bundle_id": kwargs["bundle_id"],
        },
    )
    monkeypatch.setattr(
        "hbqrs.batch.run_judge",
        lambda **kwargs: (
            pytest.fail("single-score output must be empty before run_judge")
            if Path(kwargs["output_dir"]).exists() and any(Path(kwargs["output_dir"]).iterdir())
            else single_calls.append(kwargs) or {"status": "SCORED"}
        ),
    )
    manifest = _manifest(tmp_path, "individual")
    manifest["jobs"][1]["workflow"] = "single"
    brief = tmp_path / "brief.txt"
    driving = tmp_path / "driving.txt"
    brief.write_text("Original brief.", encoding="utf-8")
    driving.write_text("Original driving prompt.", encoding="utf-8")
    manifest["jobs"][1]["brief_paths"] = [brief.name]
    manifest["jobs"][1]["driving_prompt_file"] = driving.name
    original_fake = batch_module.run_longform_judge

    def mutating_route(**kwargs):
        result = original_fake(**kwargs)
        if kwargs["plan_only"] and Path(kwargs["artifact_path"]).name == "two.txt":
            Path(kwargs["artifact_path"]).write_text("MUTATED ARTIFACT", encoding="utf-8")
            brief.write_text("MUTATED BRIEF", encoding="utf-8")
            driving.write_text("MUTATED DRIVING", encoding="utf-8")
        return result

    monkeypatch.setattr("hbqrs.batch.run_longform_judge", mutating_route)
    run_longform_batch(
        _write_manifest(tmp_path, manifest),
        registry=registry_path(), bundles=bundles_path(), allow_remote=True,
    )
    assert len(longform_calls) == 2  # one full long-form run and one route-only single pass
    assert longform_calls[0]["plan_only"] is False
    assert longform_calls[1]["plan_only"] is True
    assert len(single_calls) == 1
    assert single_calls[0]["bundle_id"] == "prose.novel"
    proof = single_calls[0]["longform_scope_compatibility_proof"]
    assert proof["mode"] == "longform_prevalidated_route"
    assert proof["artifact_id"] == "two"
    assert proof["bundle_id"] == "prose.novel"
    assert Path(single_calls[0]["artifact_path"]).read_text(encoding="utf-8") == "Chapter One\n\nA test scene.\n"
    assert [path.read_text(encoding="utf-8") for path in single_calls[0]["context_paths"]] == [
        "Original brief.", "Original driving prompt.",
    ]


def test_single_batch_rejects_a_task_contract_that_drifted_after_route_planning(
    tmp_path: Path, monkeypatch
) -> None:
    calls: list[dict[str, object]] = []
    _install_fake(monkeypatch, calls)
    manifest = _manifest(tmp_path, "individual")
    manifest["jobs"][1]["workflow"] = "single"
    drifted = tmp_path / "drifted-contract.json"
    drifted.write_text(json.dumps({"different": "contract"}), encoding="utf-8")
    manifest["defaults"]["task_contract_path"] = drifted.name
    with pytest.raises(HBQError, match="task contract drifted"):
        run_longform_batch(
            _write_manifest(tmp_path, manifest), registry=registry_path(), bundles=bundles_path(),
            allow_remote=True,
        )


def test_single_batch_rejects_an_empty_task_contract_after_route_planning(
    tmp_path: Path, monkeypatch
) -> None:
    calls: list[dict[str, object]] = []
    _install_fake(monkeypatch, calls)
    manifest = _manifest(tmp_path, "individual")
    manifest["jobs"][1]["workflow"] = "single"
    drifted = tmp_path / "drifted-contract.json"
    drifted.write_text("{}", encoding="utf-8")
    manifest["defaults"]["task_contract_path"] = drifted.name
    with pytest.raises(HBQError, match="task contract drifted"):
        run_longform_batch(
            _write_manifest(tmp_path, manifest), registry=registry_path(), bundles=bundles_path(),
            allow_remote=True,
        )
