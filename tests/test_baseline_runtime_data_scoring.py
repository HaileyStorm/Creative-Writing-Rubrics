from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "evaluation-results/hbq-human-alignment-dryad-full-hbq-analysis-v1"
SOURCE = PACKAGE / "baseline_runtime_data_scoring.py"
V1 = PACKAGE / "baseline_native_runtime.py"
V5 = PACKAGE / "baseline_native_runtime_v5.py"
EPOCH = Path(r"C:\Users\Haile\Documents\cwr-dryad-grok-local254-continuation-20260910-r1\suffix-epoch.json")
SNAPSHOT = Path(r"C:\Users\Haile\Documents\cwr-historical-schema-snapshot-20260912-r1\snapshot-manifest.json")
SNAPSHOT_SHA = "b899f5cd789e840f134b95fec457ed02f4a3a7e9f448e7d0e3b635e90665fdd4"
V1_MANIFEST = PACKAGE / "baseline-runtime-v1.json"
V1_MANIFEST_SHA = "3b1f70a40a6dac8028d11c52f747400ab88dff3a193f828e3940c53813f3273d"


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def load(path: Path, name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def subject() -> ModuleType:
    return load(SOURCE, "baseline_runtime_data_scoring_test")


def inputs() -> dict[str, Any]:
    epoch = json.loads(EPOCH.read_bytes())
    return {
        "scoring_manifest_path": V1_MANIFEST,
        "expected_scoring_manifest_sha256": V1_MANIFEST_SHA,
        "v5_runtime_manifest_path": Path(epoch["runtime_manifest"]["path"]),
        "expected_v5_runtime_manifest_sha256": epoch["runtime_manifest"]["sha256"],
        "v5_runtime_package_root": Path(epoch["runtime_package"]["root"]),
        "expected_v5_runtime_package_manifest_sha256": epoch["runtime_package"]["manifest_sha256"],
        "snapshot_manifest_path": SNAPSHOT,
        "expected_snapshot_manifest_sha256": SNAPSHOT_SHA,
    }


def run() -> tuple[dict[str, Any], dict[Path, bytes]]:
    return subject().runtime_parity_with_data(load(V1, "v1_scoring_test"), load(V5, "v5_scoring_test"), **inputs())


def test_actual_v1_v5_scoring_parity_is_bound_to_historical_data() -> None:
    record, captured = run()
    parity = record["parity"]
    assert record["v1_manifest"] == {"sha256": V1_MANIFEST_SHA, "bytes": len(V1_MANIFEST.read_bytes())}
    assert record["commitment_sha256"] == sha((json.dumps(parity, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode())
    assert parity["before_after_verified"] is True
    assert set(parity["case_score_sha256"]) == {"four_state", "not_applicable", "unknown", "weighted", "hard_gate_yes", "hard_gate_no", "hard_gate_unknown"}
    assert parity["modules_sha256"] and parity["bundle_sha256"] and parity["compiled_bundle_sha256"] and parity["question_order_sha256"]
    assert set(parity["dependency_closure"]) == {"src/hbqrs/core.py", "src/hbqrs/weights.py", "src/hbqrs/paths.py", "registry/all_modules.json", "bundles/all_bundles.json", "schema/hbq_weight_profile.schema.json"}
    provenance = record["runtime_data_provenance"]
    assert provenance["historical_schema"]["sha256"] == "49c7d824ba5dd957e67968ba3ae6ceb8a7ed9434dfb0dfc654836a76613c7854"
    assert provenance["v1"]["manifest"]["sha256"] == V1_MANIFEST_SHA
    assert provenance["v1"]["snapshot_constructor"]["identity"] == "v4_snapshot_constructor_reused_for_original_v1_scoring_loader"
    assert SNAPSHOT.resolve() in captured
    assert Path(provenance["historical_schema"]["path"]).resolve() in captured
    assert V1.resolve() in captured and V5.resolve() in captured


def test_rejects_misbound_manifest_and_snapshot_data() -> None:
    values = inputs()
    with pytest.raises(ValueError, match="v1 scoring manifest hash drift"):
        subject().runtime_parity_with_data(load(V1, "v1_scoring_bad_manifest"), load(V5, "v5_scoring_bad_manifest"), **{**values, "expected_scoring_manifest_sha256": "0" * 64})
    with pytest.raises(ValueError, match="runtime data snapshot manifest schema differs"):
        subject().runtime_parity_with_data(load(V1, "v1_scoring_bad_data"), load(V5, "v5_scoring_bad_data"), **{**values, "snapshot_manifest_path": V1_MANIFEST, "expected_snapshot_manifest_sha256": V1_MANIFEST_SHA})
