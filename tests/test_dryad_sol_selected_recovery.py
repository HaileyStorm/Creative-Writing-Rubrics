from __future__ import annotations

import importlib.util
import json
import threading
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
EXECUTION = ROOT / "evaluation-results" / "hbq-human-alignment-dryad-full-hbq-analysis-v1" / "sol_selected_recovery_execution.py"


def load() -> Any:
    spec = importlib.util.spec_from_file_location("dryad_selected_recovery_test", EXECUTION)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Runtime:
    def __init__(self, *, fail: int | None = None) -> None:
        self.fail = fail
        self.calls: list[int] = []
        self.lock = threading.Lock()

    def call_codex(self, **kwargs: Any) -> tuple[str, dict[str, Any]]:
        ordinal = kwargs["batch_number"]
        kwargs["before_provider_attempt"]()
        with self.lock:
            self.calls.append(ordinal)
        if ordinal == self.fail:
            raise ValueError("fixture failure")
        output = Path(kwargs["output_dir"]); responses = output / "responses"; responses.mkdir(parents=True)
        content = json.dumps({"verdicts": [{"question_id": f"q-{ordinal}"}]})
        (responses / f"batch-{ordinal:04d}.attempt-0001.message.json").write_text(content, encoding="utf-8")
        (responses / f"batch-{ordinal:04d}.attempt-0001.events.jsonl").write_text("{}", encoding="utf-8")
        (responses / f"batch-{ordinal:04d}.attempt-0001.stderr.bin").write_bytes(b"")
        return content, {"completion_class": "completed", "native_thread_id": f"new-{ordinal}"}


def install(monkeypatch: pytest.MonkeyPatch, value: Any, root: Path, runtime: Runtime) -> dict[str, Any]:
    plan = root / "plan"; plan.mkdir(); (plan / "plan.json").write_bytes(b"plan")
    prefix = root / "prefix.json"; prefix.write_bytes(b"prefix")
    descriptor = {"selected_request_ordinals": list(range(1, 1611)) + list(range(4049, 4739))}
    descriptor_raw = value._canonical(descriptor)
    manifest = {
        "driver_sha256": value._sha(Path(value.__file__).read_bytes()), "frozen_collector_sha256": value.OLD_SHA256,
        "frozen_runtime_sha256": value.RUNTIME_SHA256, "capture_sha256": value.CAPTURE_SHA256,
        "replacement_ordinals": list(value.REPLACEMENTS), "untouched_ordinals": list(value.UNTOUCHED),
        "counts": {"selected_collection": value.SELECTED_COUNT}, "plan_root": str(plan),
        "original_plan_sha256": value._sha(b"plan"), "selected_schedule_sha256": value._sha(descriptor_raw),
        "old_campaign_root": str(root / "old"), "prefix_replay_path": str(prefix),
        "prefix_replay_sha256": value._sha(prefix.read_bytes()), "authority_root": str(root / "authority"), "old_route_identity": {},
        "allowance_policy": "owner_assumed_allowance_no_fresh_evidence", "authority_sha256": {},
    }
    (root / "campaign-manifest.json").write_bytes(value._canonical(manifest)); (root / "selected-schedule.json").write_bytes(descriptor_raw)

    class Helper:
        @staticmethod
        def route_snapshot(_queue: Path, _identity: dict[str, Any]) -> dict[str, Any]:
            return {"codex_command": ["fixture-codex"]}

        @staticmethod
        def request_payload(_plan: Path, ordinal: int) -> tuple[dict[str, Any], bytes, bytes]:
            prompt = b"{}"
            return {"ordinal": ordinal, "batch_number": ordinal, "question_ids": [f"q-{ordinal}"],
                    "prompt_sha256": value._sha(prompt), "schema_sha256": value._sha(prompt)}, prompt, prompt

    def completed(slot: Path, request: dict[str, Any], adapter: Runtime) -> tuple[str, dict[str, Any]]:
        record = json.loads((slot / "provider-record.json").read_bytes())
        return record["native_thread_id"], record

    old = SimpleNamespace(PARALLEL=Path("parallel"), PARALLEL_SHA256="parallel", _load=lambda *_args: SimpleNamespace(HELPER_PATH=Path("helper"), HELPER_SHA="helper", _load=lambda *_args: Helper), _validated_completion=completed)
    schedule = SimpleNamespace(canonical=value._canonical, verify_selected_schedule=lambda **kwargs: kwargs["descriptor"])
    monkeypatch.setattr(value, "_load", lambda path, *_args: schedule if path == value.SCHEDULE else old)
    monkeypatch.setattr(value, "_static", lambda *_args: (old, runtime, {"thread_ids": [f"old-{item}" for item in range(value.PREFIX_COUNT)]}, {}))
    monkeypatch.setattr(value, "_authority", lambda *_args: ({}, {}, {"records": []}, {}))
    monkeypatch.setattr(value, "_old_campaign", lambda *_args: set())
    return manifest


def test_phase_one_replacements_precede_untouched_collection(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    value = load(); root = tmp_path / "campaign"; root.mkdir(); runtime = Runtime(); install(monkeypatch, value, root, runtime)

    result = value.dispatch(campaign_root=root, queue_root=tmp_path, adapter_override=runtime)

    assert result["state"] == "collected", result["failures"]
    assert set(runtime.calls[: len(value.REPLACEMENTS)]) == set(value.REPLACEMENTS)
    assert set(runtime.calls[len(value.REPLACEMENTS):]) == set(value.UNTOUCHED)
    replacement = json.loads((root / "requests" / "4295" / "start.json").read_bytes())
    untouched = json.loads((root / "requests" / "4306" / "start.json").read_bytes())
    assert replacement["logical_attempt"] == 2 and replacement["phase"] == "owner_authorized_transport_replacement"
    assert untouched["logical_attempt"] == 1 and untouched["phase"] == "untouched"


def test_phase_one_failure_drains_without_submitting_untouched(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    value = load(); root = tmp_path / "campaign"; root.mkdir(); runtime = Runtime(fail=value.REPLACEMENTS[0]); install(monkeypatch, value, root, runtime)

    result = value.dispatch(campaign_root=root, queue_root=tmp_path, adapter_override=runtime)

    assert result["state"] == "stopped_no_retry" and result["phase"] == "owner_authorized_transport_replacement"
    assert set(runtime.calls).issubset(value.REPLACEMENTS)
    assert not (root / "requests" / "4306").exists()
    assert json.loads((root / "requests" / "4295" / "terminal.json").read_bytes())["state"] == "stopped_no_retry"


def test_bad_manifest_or_descriptor_aborts_before_contact(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    value = load(); root = tmp_path / "campaign"; root.mkdir(); runtime = Runtime(); manifest = install(monkeypatch, value, root, runtime)
    manifest["driver_sha256"] = "0" * 64; (root / "campaign-manifest.json").write_bytes(value._canonical(manifest))
    with pytest.raises(ValueError, match="manifest differs"):
        value.dispatch(campaign_root=root, queue_root=tmp_path, adapter_override=runtime)
    assert runtime.calls == []
    manifest["driver_sha256"] = value._sha(Path(value.__file__).read_bytes()); (root / "campaign-manifest.json").write_bytes(value._canonical(manifest))
    (root / "selected-schedule.json").write_bytes(b"{}")
    with pytest.raises(ValueError, match="selected schedule differs"):
        value.dispatch(campaign_root=root, queue_root=tmp_path, adapter_override=runtime)
    assert runtime.calls == []


def test_existing_incomplete_slot_rejects_without_resend(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    value = load(); root = tmp_path / "campaign"; root.mkdir(); runtime = Runtime(); install(monkeypatch, value, root, runtime)
    slot = root / "requests" / "4295"; slot.mkdir(parents=True); (slot / "terminal.json").write_bytes(value._canonical({"state": "stopped_no_retry"}))

    with pytest.raises(ValueError, match="incomplete recovery slot"):
        value.dispatch(campaign_root=root, queue_root=tmp_path, adapter_override=runtime)

    assert runtime.calls == []


def test_precontact_gate_rejects_changed_authority_or_payload(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    value = load(); root = tmp_path / "authority"; root.mkdir(); runtime = Runtime(); install(monkeypatch, value, root, runtime)
    monkeypatch.setattr(value, "_authority", lambda *_args: (_ for _ in ()).throw(ValueError("wrong authority")))

    with pytest.raises(ValueError, match="wrong authority"):
        value.dispatch(campaign_root=root, queue_root=tmp_path, adapter_override=runtime)
    assert runtime.calls == []

    class TamperingRuntime(Runtime):
        def call_codex(self, **kwargs: Any) -> tuple[str, dict[str, Any]]:
            (Path(kwargs["output_dir"]) / "payload" / "prompt.txt").write_bytes(b"changed")
            return super().call_codex(**kwargs)

    root = tmp_path / "payload"; root.mkdir(); tampered = TamperingRuntime(); install(monkeypatch, value, root, tampered)
    monkeypatch.setattr(value, "_authority", lambda *_args: ({}, {}, {"records": []}, {}))
    stopped = value.dispatch(campaign_root=root, queue_root=tmp_path, adapter_override=tampered)

    assert stopped["state"] == "stopped_no_retry" and tampered.calls == []


def test_manifest_requires_the_authority_hash_map_before_contact(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    value = load(); root = tmp_path / "campaign"; root.mkdir(); runtime = Runtime(); install(monkeypatch, value, root, runtime)
    monkeypatch.setattr(value, "_authority", lambda *_args: ({}, {}, {"records": []}, {"adoption": "a" * 64}))

    with pytest.raises(ValueError, match="authority manifest binding"):
        value.dispatch(campaign_root=root, queue_root=tmp_path, adapter_override=runtime)
    assert runtime.calls == []


def test_prepare_rejects_a_plan_or_schedule_not_owned_by_the_old_manifest(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    value = load(); plan = tmp_path / "plan"; plan.mkdir(); (plan / "plan.json").write_bytes(b"plan")
    descriptor = {"selected_request_ordinals": list(range(1, 1611)) + list(range(4049, 4739))}; descriptor_raw = value._canonical(descriptor)
    schedule = SimpleNamespace(canonical=value._canonical, verify_selected_schedule=lambda **kwargs: kwargs["descriptor"])
    monkeypatch.setattr(value, "_load", lambda *_args: schedule)
    monkeypatch.setattr(value, "_static", lambda *_args: (None, None, {"thread_ids": []}, {"plan_root": str(tmp_path / "other"),
                                                              "original_plan_sha256": value._sha(b"plan"), "selected_schedule_sha256": value._sha(descriptor_raw)}))
    monkeypatch.setattr(value, "_authority", lambda *_args: ({"replacement_class": "owner_authorized_transport_replacement"}, {}, {}, {}))

    with pytest.raises(ValueError, match="old selected plan or schedule"):
        value.prepare_campaign(campaign_root=tmp_path / "campaign", old_campaign_root=tmp_path / "old", plan_root=plan,
                               selected_schedule=descriptor, selected_schedule_sha256=value._sha(descriptor_raw),
                               expected_plan_sha256=value._sha(b"plan"), prefix_replay_path=tmp_path / "prefix", expected_prefix_replay_sha256="a" * 64)


def test_failed_slot_inventory_binds_event_id_and_all_artifacts(tmp_path: Path) -> None:
    value = load(); old = tmp_path / "old"; old.mkdir(); result = old / "collection-result.json"; result.write_bytes(b"result")
    records: list[dict[str, Any]] = []
    for ordinal in value.REPLACEMENTS:
        slot = old / "requests" / f"{ordinal:04d}"; events = slot / "native-output" / "responses" / "events.events.jsonl"; events.parent.mkdir(parents=True)
        events.write_text(json.dumps({"type": "thread.started", "thread_id": f"failed-{ordinal}"}) + "\n", encoding="utf-8")
        records.append({"ordinal": ordinal, "slot_path": str(slot), "files": {events.relative_to(slot).as_posix(): {"sha256": value._sha(events.read_bytes())}}})
    incident = {"collection_result_sha256": value._sha(result.read_bytes()), "records": records}

    assert value._old_campaign(incident, old) == {f"failed-{ordinal}" for ordinal in value.REPLACEMENTS}
    (old / "requests" / "4295" / "native-output" / "responses" / "events.events.jsonl").write_text("{}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="failed artifact"):
        value._old_campaign(incident, old)


def test_completed_slot_delegates_to_the_frozen_resume_validator(tmp_path: Path) -> None:
    value = load(); root = tmp_path / "campaign"; slot = root / "requests" / "4295"; slot.mkdir(parents=True)
    manifest_sha = "m" * 64; start = {"ordinal": 4295, "attempt": 1, "logical_attempt": 2, "phase": "owner_authorized_transport_replacement"}
    (slot / "start.json").write_bytes(value._canonical(start)); (slot / "source-bindings.json").write_bytes(value._canonical({"manifest_sha256": manifest_sha}))
    (slot / "authorization.json").write_bytes(value._canonical({"manifest_sha256": manifest_sha, "replacement_class": "owner_authorized_transport_replacement"}))
    (slot / "terminal.json").write_bytes(value._canonical({"state": "completed", "phase": start["phase"], "logical_attempt": 2,
                                                              "replacement_class": "owner_authorized_transport_replacement"}))
    seen: list[bool] = []
    old = SimpleNamespace(_completed=lambda *args, **kwargs: seen.append(True) or True)

    assert value._completed(root, {"ordinal": 4295}, set(), old=old, runtime=object(), manifest_sha256=manifest_sha)
    assert seen == [True]


def test_prefix_receipt_hash_and_artifact_inventory_are_required(tmp_path: Path) -> None:
    value = load(); old = tmp_path / "old"; slot = old / "requests" / "1343"; slot.mkdir(parents=True)
    prefix_ids = [f"prefix-{item}" for item in range(1342)]
    (slot / "terminal.json").write_bytes(value._canonical({"state": "completed", "thread_id": "new-prefix"}))
    receipt = {"evidence_class": "selected100_sol_stopped_successful_prefix_independent_replay", "recognized_logical_requests": value.PREFIX_COUNT,
               "recognized_verdicts": 14376, "manifest_sha256": value.OLD_MANIFEST_SHA256, "collection_result_sha256": "2d9dc66229f111311e5957696788b67a7a0e797b737c94c6a3f8506ab535cd7b",
               "prefix_replay_sha256": "69bf33fde6bba29d715d38186b74617db8c10a54f93569e22d5fbaa57242f5de", "source_driver_sha256": value.OLD_SHA256,
               "source_runtime_sha256": value.RUNTIME_SHA256, "accepted_via_existing_paths": 1847, "old_unknown_exit_recoveries": 10,
               "failed_requests": 10, "unique_accepted_native_threads": value.PREFIX_COUNT, "untouched_requests": len(value.UNTOUCHED),
               "provider_calls_this_replay": 0, "resend_authority": False, "full_study_admitted": False, "new_zero_exit_completed_requests": 515,
               "records": [{"ordinal": 1343, "files": {"terminal.json": value._sha((slot / "terminal.json").read_bytes())}}]}
    path = tmp_path / "prefix.json"; path.write_bytes(value._canonical(receipt))
    with pytest.raises(ValueError, match="completed inventory differs"):
        value._prefix(path, value._sha(path.read_bytes()), old, {"prefix": {"thread_ids": prefix_ids}})
    with pytest.raises(ValueError, match="prefix replay differs"):
        value._prefix(path, "0" * 64, old, {"prefix": {"thread_ids": prefix_ids}})
