from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "evaluation-results/hbq-human-alignment-dryad-full-hbq-analysis-v1/baseline_runtime_data_snapshot_v4.py"
EPOCH = Path(r"C:\Users\Haile\Documents\cwr-dryad-grok-local254-continuation-20260910-r1\suffix-epoch.json")
SNAPSHOT = Path(r"C:\Users\Haile\Documents\cwr-historical-schema-snapshot-20260912-r1\snapshot-manifest.json")
SNAPSHOT_SHA = "b899f5cd789e840f134b95fec457ed02f4a3a7e9f448e7d0e3b635e90665fdd4"


def load() -> Any:
    spec = importlib.util.spec_from_file_location("baseline_runtime_data_snapshot_v4_test", SOURCE)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def epoch() -> dict[str, Any]:
    return json.loads(EPOCH.read_bytes())


def test_snapshot_rejects_wrong_missing_and_mutated_schema(tmp_path: Path) -> None:
    value = load()
    with pytest.raises(ValueError, match="snapshot manifest differs"):
        value._snapshot(SNAPSHOT, "0" * 64)
    missing_manifest = json.loads(SNAPSHOT.read_bytes())
    missing_manifest["snapshot"]["path"] = str(tmp_path / "missing.json")
    missing_path = tmp_path / "missing-manifest.json"
    missing_raw = json.dumps(missing_manifest, sort_keys=True).encode()
    missing_path.write_bytes(missing_raw)
    with pytest.raises(ValueError, match="snapshot storage missing"):
        value._snapshot(missing_path, sha(missing_raw))
    altered = tmp_path / "altered.json"
    altered.write_bytes(b"{}\n")
    changed_manifest = json.loads(SNAPSHOT.read_bytes())
    changed_manifest["snapshot"] = {"path": str(altered), "bytes": 3, "sha256": sha(b"{}\n")}
    changed_path = tmp_path / "changed-manifest.json"
    changed_raw = json.dumps(changed_manifest, sort_keys=True).encode()
    changed_path.write_bytes(changed_raw)
    with pytest.raises(ValueError, match="snapshot bindings"):
        value._snapshot(changed_path, sha(changed_raw))


def test_runtime_rejects_v4_epoch_mapping_and_source_drift(monkeypatch: pytest.MonkeyPatch) -> None:
    value = load()
    broken = epoch()
    broken["old_runtime_loader"] = {**broken["old_runtime_loader"], "sha256": "0" * 64}
    with pytest.raises(ValueError, match="V4 bindings"):
        value.load_old_runtime_from_epoch(broken, snapshot_manifest_path=SNAPSHOT, expected_snapshot_manifest_sha256=SNAPSHOT_SHA)
    original_read = Path.read_bytes

    def altered_read(path: Path) -> bytes:
        if path.resolve() == value.V4.resolve():
            return b"changed"
        return original_read(path)

    monkeypatch.setattr(Path, "read_bytes", altered_read)
    with pytest.raises(ValueError, match="V4 runtime loader differs"):
        value.load_old_runtime_from_epoch(epoch(), snapshot_manifest_path=SNAPSHOT, expected_snapshot_manifest_sha256=SNAPSHOT_SHA)


def test_runtime_uses_old_schema_and_preserves_all_current_shared_pins(monkeypatch: pytest.MonkeyPatch) -> None:
    value = load()
    canonical_before = (ROOT / "schema/hbq_judge_response.schema.json").read_bytes()
    runtime = value.load_old_runtime_from_epoch(epoch(), snapshot_manifest_path=SNAPSHOT, expected_snapshot_manifest_sha256=SNAPSHOT_SHA)
    old_schema = json.loads(Path(r"C:\Users\Haile\Documents\cwr-historical-schema-snapshot-20260912-r1\schema\hbq_judge_response.schema.json").read_bytes())
    assert runtime.runner._response_schema() == old_schema
    assert (ROOT / "schema/hbq_judge_response.schema.json").read_bytes() == canonical_before
    assert runtime.runner.__file__ == str(ROOT / "src/hbqrs/runner.py")
    assert runtime.core.__file__ == str(ROOT / "src/hbqrs/core.py")
    assert runtime.transport.__file__ == str(ROOT / "src/hbqrs/grok_broker_transport_v2.py")
    provenance = runtime.provenance
    assert provenance["evidence_class"] == "constructor_verified_v4_runtime_with_explicit_historical_data_snapshot"
    assert provenance["code"]["runtime_loader"] == {"path": str(SOURCE.resolve()), "sha256": sha(SOURCE.read_bytes())}
    assert provenance["code"]["historical_v4_runtime_loader"] == {"path": str(value.V4), "sha256": value.V4_SHA256}
    assert provenance["code"]["frozen_snapshot_helpers"] == {"path": str(value.SNAPSHOT_HELPERS), "sha256": value.SNAPSHOT_HELPERS_SHA256}
    assert provenance["code"]["historical_helper"]["sha256"] == "d98686761c4af296c4132a477bc54c3bcdfc3bb8b0140ffd2681919652fe81f9"
    manifest = json.loads((ROOT / "evaluation-results/hbq-human-alignment-dryad-full-hbq-analysis-v1/baseline-runtime-v1.json").read_bytes())
    assert runtime.transport_sha256 == manifest["bridge_sha256"]
    sources = provenance["source_sha256"]
    for relative, expected in manifest["shared_runtime_bindings"].items():
        path = str((Path.home() / ".codex/tools/model_work_queue" / relative).resolve())
        assert sources[path] == expected
    pins = provenance["data"]["schema_pins"]
    assert [item["logical_path"] for item in pins] == ["schema/hbq_judge_response.schema.json", "schema/hbq_verdict.schema.json", "schema/hbq_weight_profile.schema.json"]
    record = runtime.runner._read_text_record(ROOT / "schema/hbq_judge_response.schema.json")
    assert record["path"] == pins[0]["storage_path"]
    assert record["sha256"] == value.OLD_SCHEMA_SHA256
    runtime.verify()
    snapshot_storage = Path(pins[0]["storage_path"]).resolve()
    snapshot_manifest = Path(provenance["data"]["snapshot_manifest"]["path"]).resolve()
    shared_storage = Path.home() / ".codex/tools/model_work_queue/broker.py"
    original_read = Path.read_bytes
    mode = "changed"

    def altered_read(path: Path) -> bytes:
        if path.resolve() == shared_storage.resolve() and mode == "shared":
            return b"changed shared source"
        if path.resolve() == snapshot_manifest and mode == "manifest":
            return b"changed manifest"
        if path.resolve() == snapshot_storage:
            if mode == "missing":
                raise FileNotFoundError(path)
            if mode != "manifest":
                return b"changed"
        return original_read(path)

    monkeypatch.setattr(Path, "read_bytes", altered_read)
    mode = "shared"
    with pytest.raises(ValueError, match="runtime source changed"):
        runtime.verify()
    mode = "changed"
    with pytest.raises(ValueError, match="runtime data changed"):
        runtime.verify()
    mode = "missing"
    with pytest.raises(ValueError, match="runtime data missing"):
        runtime.verify()
    mode = "manifest"
    with pytest.raises(ValueError, match="snapshot manifest changed"):
        runtime.verify()
