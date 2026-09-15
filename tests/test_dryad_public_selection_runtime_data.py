"""Offline regression for the public selected-successor selection seam."""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

CWR_ROOT = Path(__file__).resolve().parents[1]
ANALYSIS_TEST = CWR_ROOT / "tests" / "test_dryad_grok_successor_analysis.py"


def _load_analysis_test() -> Any:
    spec = importlib.util.spec_from_file_location(
        "cwr_selection_seam_analysis_fixture", ANALYSIS_TEST
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def _descriptor(path: Path, raw: bytes) -> dict[str, str]:
    path.write_bytes(raw)
    return {"path": str(path), "sha256": _sha(raw)}


def test_public_admission_uses_runtime_snapshot_selection_and_distinct_runtimes(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fixture = _load_analysis_test()
    subject = fixture.load()
    events: list[tuple[str, Any]] = []

    plan_root, old_suffix_root, recovery_root = (
        tmp_path / name for name in ("plan", "old-suffix", "recovery")
    )
    for root in (plan_root, old_suffix_root, recovery_root):
        root.mkdir()

    schedule_raw = _canonical({"selected": "schedule"})
    source_raw = b"selected-schedule-verifier"
    schedule = _descriptor(tmp_path / "selected-schedule.json", schedule_raw)
    schedule_source = _descriptor(tmp_path / "selected-schedule-source.py", source_raw)

    runtime_names = (
        "context_adapter",
        "snapshot_manifest",
        "prefix_adapter",
        "runtime_data_snapshot_v4",
        "runtime_data_snapshot_v5",
        "native_data_admission",
        "recovered_data_admission",
    )
    runtime_descriptors = {
        name: _descriptor(tmp_path / f"{name}.bin", name.encode())
        for name in runtime_names
    }
    runtime_data = {
        "context_adapter": runtime_descriptors["context_adapter"],
        "snapshot_manifest": runtime_descriptors["snapshot_manifest"],
        "prefix_adapter": runtime_descriptors["prefix_adapter"],
        "source_bindings": {
            name: runtime_descriptors[name]
            for name in runtime_names
            if name
            not in {"context_adapter", "snapshot_manifest", "prefix_adapter"}
        },
    }

    old_runtime = SimpleNamespace(verify=lambda: events.append(("verify-old", None)))
    suffix_runtime = SimpleNamespace(
        verify=lambda: events.append(("verify-suffix", None))
    )
    context = SimpleNamespace(
        epoch={
            "selected_schedule": schedule,
            "selected_schedule_source": schedule_source,
        },
        old_runtime=old_runtime,
        suffix_runtime=suffix_runtime,
    )

    class RuntimeAdapter:
        def build_snapshot_replay_context(self, **kwargs: Any) -> Any:
            events.append(("build-context", kwargs))
            return context

    runtime_adapter = RuntimeAdapter()

    predecessor = {
        "identity_exclusion": {"path": "unused", "sha256": "0" * 64},
        "initialization": {"kind": "initialization"},
        "ledger_head": {"kind": "ledger"},
        "recovery_manifest": {"kind": "recovery"},
    }

    class Verifier:
        def verify_selected_schedule(self, **kwargs: Any) -> dict[str, Any]:
            events.append(("verify-schedule", kwargs))
            return {
                "selected_train_ids": ["train-000"],
                "selected_dev_ids": ["dev-000"],
                "selected_request_ordinals": [1],
                "question_ids": ["q-000"],
            }

    verifier = Verifier()

    def predecessor_loader(path: Path | str, expected: str) -> tuple[bytes, dict[str, Any]]:
        events.append(("predecessor", (Path(path), expected)))
        return b"predecessor", predecessor

    def predecessor_bindings(
        actual_context: Any,
        actual_predecessor: dict[str, Any],
        **kwargs: Any,
    ) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
        assert actual_context is context
        assert actual_predecessor is predecessor
        events.append(("predecessor-bindings", kwargs))
        return (
            {"kind": "initialization-record"},
            {"kind": "original-initialization"},
            {"kind": "ledger-record"},
        )

    def read_file(path: Path | str, expected: str, label: str) -> bytes:
        checked = Path(path)
        raw = checked.read_bytes()
        assert _sha(raw) == expected
        events.append(("read", label))
        return raw

    composite = SimpleNamespace(
        _predecessor=predecessor_loader,
        _predecessor_bindings=predecessor_bindings,
        _descriptor_with_bytes=lambda value, _label: dict(value),
        _descriptor=lambda value, _label: dict(value),
        _read=read_file,
        _json=lambda raw, _label: json.loads(raw.decode()),
        _load_module=lambda *_args: verifier,
        _identity_exclusions=lambda _value: (set(), set()),
    )

    class Reader:
        def _runtime_data(self, value: dict[str, Any]) -> tuple[Any, Any, dict[str, Any]]:
            events.append(("runtime-data", value))
            return runtime_adapter, SimpleNamespace(), value

        def _verify_runtime_data_sources(self, value: dict[str, Any]) -> None:
            events.append(("verify-runtime-sources", value))

        def read_selected_successor_collection(self, **kwargs: Any) -> dict[str, Any]:
            events.append(("read-collection", kwargs))
            return {"synthetic_collection": True}

    reader = Reader()
    old = SimpleNamespace(
        _selection=lambda: pytest.fail("obsolete old._selection factory was used")
    )
    captured: dict[Path, bytes] = {}
    monkeypatch.setattr(
        subject,
        "_capture",
        lambda _pins: (
            captured,
            reader,
            SimpleNamespace(),
            old,
            composite,
            SimpleNamespace(),
            SimpleNamespace(),
            SimpleNamespace(),
            SimpleNamespace(),
        ),
    )

    admission = subject.SelectedSuccessorAdmission(
        record={"runtime_data_protected_paths": {}}, sha256="a" * 64
    )

    def admit_collection(collection: Any, actual_reader: Any, **kwargs: Any) -> Any:
        assert collection == {"synthetic_collection": True}
        assert actual_reader is reader
        events.append(("admit-collection", kwargs))
        return admission

    monkeypatch.setattr(subject, "_admit_collection", admit_collection)

    local = {
        "root": str(tmp_path / "local"),
        "manifest_sha256": "1" * 64,
        "controller_sha256": "2" * 64,
    }
    candidate = {
        "root": str(tmp_path / "candidate"),
        "manifest_sha256": "3" * 64,
        "controller_sha256": "4" * 64,
    }
    inputs = {
        "plan_root": plan_root,
        "predecessor_path": tmp_path / "predecessor.json",
        "old_suffix_root": old_suffix_root,
        "recovery_root": recovery_root,
        "expected_plan_sha256": "5" * 64,
        "expected_predecessor_sha256": "6" * 64,
        "expected_old_epoch_sha256": "7" * 64,
        "expected_suffix_source_sha256": "8" * 64,
        "expected_recovery_controller_sha256": "9" * 64,
        "expected_recovery_manifest_sha256": "a" * 64,
        "expected_public_inputs_sha256": "b" * 64,
        "approved_v4_routes": {},
        "approved_v5_routes": {},
        "successor_roots": [
            {"root": str(tmp_path / "successor"), "manifest_sha256": "c" * 64}
        ],
        "local_continuation": local,
        "candidate_native_continuation": candidate,
        "runtime_data": runtime_data,
    }
    source_pins = {key: "0" * 64 for key in subject.PIN_KEYS}
    source_pins["old_helper_closure"] = subject.OLD_HELPER_SHA256

    result = subject.admit_selected_successor(
        reader_inputs=inputs, source_pins=source_pins
    )
    assert result is admission

    collection_call = next(value for name, value in events if name == "read-collection")
    assert collection_call["runtime_data"] == runtime_data

    context_call = next(value for name, value in events if name == "build-context")
    assert context_call["suffix_root"] == old_suffix_root.resolve()
    assert context_call["plan_root"] == plan_root.resolve()
    assert context_call["expected_epoch_sha256"] == inputs["expected_old_epoch_sha256"]
    assert context_call["expected_suffix_source_sha256"] == inputs["expected_suffix_source_sha256"]
    assert context_call["snapshot_manifest_path"] == Path(
        runtime_data["snapshot_manifest"]["path"]
    )
    assert (
        context_call["expected_snapshot_manifest_sha256"]
        == runtime_data["snapshot_manifest"]["sha256"]
    )
    assert context_call["source_bindings"] == runtime_data["source_bindings"]

    assert [name for name, _value in events if name.startswith("verify-")] == [
        "verify-schedule",
        "verify-old",
        "verify-suffix",
        "verify-runtime-sources",
    ]
    selection_call = next(
        value for name, value in events if name == "admit-collection"
    )
    assert selection_call["selection"] == {
        "schedule": schedule,
        "source": schedule_source,
        "verified": {
            "selected_train_ids": ["train-000"],
            "selected_dev_ids": ["dev-000"],
            "selected_request_ordinals": [1],
            "question_ids": ["q-000"],
        },
    }
