"""Provider-free checks for the explicit runtime-data replay context."""

from __future__ import annotations

import hashlib
import importlib.util
import json
from collections.abc import Mapping
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "evaluation-results/hbq-human-alignment-dryad-full-hbq-analysis-v1"
SOURCE = PACKAGE / "baseline_runtime_data_collection_context.py"
EPOCH = Path(
    r"C:\Users\Haile\Documents\cwr-dryad-grok-local254-continuation-20260910-r1\suffix-epoch.json"
)
SNAPSHOT = Path(
    r"C:\Users\Haile\Documents\cwr-historical-schema-snapshot-20260912-r1\snapshot-manifest.json"
)
EPOCH_SHA256 = "74012a612915137c43e35eff5bb64b413be0b2dabbdc3aa52ceb4b88d1a245d6"
SNAPSHOT_SHA256 = "b899f5cd789e840f134b95fec457ed02f4a3a7e9f448e7d0e3b635e90665fdd4"


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def load() -> Any:
    spec = importlib.util.spec_from_file_location(
        "baseline_runtime_data_collection_context_test", SOURCE
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def bindings(subject: Any) -> dict[str, dict[str, str]]:
    return {
        "runtime_data_snapshot_v4": {
            "path": str(subject.V4_DATA_LOADER),
            "sha256": subject.V4_DATA_LOADER_SHA256,
        },
        "runtime_data_snapshot_v5": {
            "path": str(subject.V5_DATA_LOADER),
            "sha256": subject.V5_DATA_LOADER_SHA256,
        },
        "native_data_admission": {
            "path": str(subject.NATIVE_DATA_ADMISSION),
            "sha256": subject.NATIVE_DATA_ADMISSION_SHA256,
        },
    }


@pytest.fixture(scope="module")
def context() -> SimpleNamespace:
    subject = load()
    epoch_raw = EPOCH.read_bytes()
    assert digest(epoch_raw) == EPOCH_SHA256
    epoch = json.loads(epoch_raw)
    prefix = json.loads(Path(epoch["old_prefix_manifest"]["path"]).read_bytes())
    return SimpleNamespace(
        subject=subject,
        value=subject.build_snapshot_replay_context(
            suffix_root=EPOCH.parent,
            plan_root=Path(epoch["plan_root"]),
            expected_epoch_sha256=EPOCH_SHA256,
            expected_suffix_source_sha256=epoch["executor_source"]["sha256"],
            predecessor={
                "recovery_manifest": {
                    "sha256": prefix["anchors"]["grok51_manifest_sha256"]
                }
            },
            snapshot_manifest_path=SNAPSHOT,
            expected_snapshot_manifest_sha256=SNAPSHOT_SHA256,
            source_bindings=bindings(subject),
        ),
    )


def test_builds_actual_provider_free_context_with_paired_runtime_data(
    context: SimpleNamespace,
) -> None:
    value = context.value
    assert value.epoch["plan_root"] == str(value.plan_root)
    assert len(value.old_passes) == 3
    assert value.old_snapshot_descriptor["epoch"] == {
        "path": str(EPOCH),
        "sha256": EPOCH_SHA256,
    }
    assert (
        value.old_snapshot_descriptor["schema"]
        == value.old_runtime.provenance["data"]["schema_pins"][0]
    )
    assert (
        value.suffix_snapshot_descriptor["schema"]
        == value.suffix_runtime.provenance["data"]["schema_pins"][0]
    )
    assert (
        value.old_runtime.provenance["code"]["runtime_loader"]["sha256"]
        == context.subject.V4_DATA_LOADER_SHA256
    )
    assert (
        value.suffix_runtime.provenance["code"]["runtime_loader"]["sha256"]
        == context.subject.V5_DATA_LOADER_SHA256
    )
    value.old_runtime.verify()
    value.suffix_runtime.verify()


@pytest.mark.parametrize(
    "key", ["runtime_data_snapshot_v4", "runtime_data_snapshot_v5"]
)
def test_rejects_runtime_loader_source_drift(
    context: SimpleNamespace, key: str
) -> None:
    epoch = json.loads(EPOCH.read_bytes())
    prefix = json.loads(Path(epoch["old_prefix_manifest"]["path"]).read_bytes())
    source_bindings = bindings(context.subject)
    source_bindings[key]["sha256"] = "0" * 64
    with pytest.raises(ValueError, match="runtime-data loader binding differs"):
        context.subject.build_snapshot_replay_context(
            suffix_root=EPOCH.parent,
            plan_root=Path(epoch["plan_root"]),
            expected_epoch_sha256=EPOCH_SHA256,
            expected_suffix_source_sha256=epoch["executor_source"]["sha256"],
            predecessor={
                "recovery_manifest": {
                    "sha256": prefix["anchors"]["grok51_manifest_sha256"]
                }
            },
            snapshot_manifest_path=SNAPSHOT,
            expected_snapshot_manifest_sha256=SNAPSHOT_SHA256,
            source_bindings=source_bindings,
        )


def test_rejects_snapshot_schema_binding_drift(context: SimpleNamespace) -> None:
    epoch = json.loads(EPOCH.read_bytes())
    prefix = json.loads(Path(epoch["old_prefix_manifest"]["path"]).read_bytes())
    with pytest.raises(ValueError, match="snapshot manifest differs"):
        context.subject.build_snapshot_replay_context(
            suffix_root=EPOCH.parent,
            plan_root=Path(epoch["plan_root"]),
            expected_epoch_sha256=EPOCH_SHA256,
            expected_suffix_source_sha256=epoch["executor_source"]["sha256"],
            predecessor={
                "recovery_manifest": {
                    "sha256": prefix["anchors"]["grok51_manifest_sha256"]
                }
            },
            snapshot_manifest_path=SNAPSHOT,
            expected_snapshot_manifest_sha256="0" * 64,
            source_bindings=bindings(context.subject),
        )


def test_old_adapter_uses_explicit_runtime_and_never_calls_frozen_runtime_factory(
    context: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    value = context.value
    pass_record = json.loads((value.plan_root / "plan.json").read_bytes())["passes"][0]
    observed: dict[str, Any] = {}

    def factory(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("frozen old runtime factory entered")

    class Adapter:
        @staticmethod
        def admit_pass_with_runtime_data(
            run_root: Path, **kwargs: Any
        ) -> dict[str, Any]:
            observed["run_root"] = run_root
            observed.update(kwargs)
            return {"ok": True}

    original_load = context.subject._load_bound_module

    def load_bound(descriptor: Any, label: str) -> Any:
        if label == "native data admission":
            return Adapter
        return original_load(descriptor, label)

    monkeypatch.setattr(value.suffix, "_old_runtime_from_epoch", factory)
    monkeypatch.setattr(context.subject, "_load_bound_module", load_bound)
    result = context.subject.admit_old_with_runtime_data(
        value,
        plan_root=value.plan_root,
        pass_record=pass_record,
        run_root=Path(value.old_passes[0]["run_root"]),
        approved_v4_routes={"route": {}},
    )
    assert result == {"ok": True}
    assert observed["runtime"] is value.old_runtime
    assert observed["snapshot_descriptor"] == value.old_snapshot_descriptor
    assert observed["batch_size"] == 8
    assert observed["source"]["opaque_story_id"] == pass_record["logical_sample_id"]


def test_recovered70_uses_explicit_old_runtime_and_preserves_v5_suffix_replay(
    context: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    value = context.value
    value.source_bindings["recovered_data_admission"] = {
        "path": str(PACKAGE / "baseline_recovered_data_admission.py"),
        "sha256": "cee3fa24b15031632ced4681e69fdd8c5ee0119728d768b0026db46ad66a0997",
    }
    identity_offset = 900_000

    def identities(count: int, start: int) -> list[dict[str, Any]]:
        return [
            {
                "request_id_hash": f"{start + number:064x}",
                "session_id_hash": f"{start + 500_000 + number:064x}",
                "observed_turns": 1,
            }
            for number in range(count)
        ]

    class NativeAdapter:
        @staticmethod
        def admit_pass_with_runtime_data(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
            current = len(native_calls) * 23
            native_calls.append(current)
            return {"native_identities": identities(23, identity_offset + current)}

    class RecoveredAdapter:
        @staticmethod
        def admit_prefix_with_runtime_data(
            *_args: Any, **kwargs: Any
        ) -> dict[str, Any]:
            assert kwargs["runtime"] is value.old_runtime
            assert kwargs["snapshot_descriptor"] == value.old_snapshot_descriptor
            return {
                "evidence_class": "mixed_native_and_study_recovered_record_replay",
                "native_record_count": 10,
                "study_recovered_record_count": 1,
                "study_recovered_ordinals": [70],
                "verdicts": [
                    {"question_id": item["question"]["id"], "verdict": "YES"}
                    for item in value.old_runtime.questions[:88]
                ],
                "native_identities": identities(10, identity_offset + 100),
            }

    native_calls: list[int] = []
    original_load = context.subject._load_bound_module

    def load_bound(descriptor: Any, label: str) -> Any:
        if label == "native data admission":
            return NativeAdapter
        if label == "recovered data admission":
            return RecoveredAdapter
        return original_load(descriptor, label)

    def replay_terminal(
        *, row: Mapping[str, Any], **_kwargs: Any
    ) -> tuple[list[dict[str, Any]], dict[str, str]]:
        ordinal = row["ordinal"]
        return (
            [
                {"question_id": question_id, "verdict": "YES"}
                for question_id in row["question_ids"]
            ],
            {
                "request_id_hash": f"{1_500_000 + ordinal:064x}",
                "session_id_hash": f"{2_000_000 + ordinal:064x}",
            },
        )

    monkeypatch.setattr(context.subject, "_load_bound_module", load_bound)
    monkeypatch.setattr(
        value.suffix, "_require_wave_settlement", lambda *_args, **_kwargs: None
    )
    monkeypatch.setattr(value.suffix, "_replay_suffix_terminal", replay_terminal)
    monkeypatch.setattr(value.suffix, "_completed_v5_identities", lambda *_args: [])
    result = context.subject.admit_suffix_with_runtimes(
        value,
        suffix_root=EPOCH.parent,
        expected_epoch_sha256=EPOCH_SHA256,
        pass_id=json.loads((value.plan_root / "plan.json").read_bytes())["passes"][3][
            "pass_id"
        ],
        approved_v4_routes={"route": {}},
        approved_v5_routes={},
    )
    assert native_calls == [0, 23, 46]
    assert (
        result["old_v4_native_records"] == 10 and result["old_recovered70_records"] == 1
    )
    assert (
        result["new_v5_native_records"] == 12 and len(result["native_identities"]) == 91
    )
    assert result["provider_calls_made"] == 0
