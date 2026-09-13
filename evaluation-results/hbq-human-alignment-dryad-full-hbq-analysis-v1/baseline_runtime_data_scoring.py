"""Bind frozen scoring parity to the explicit historical schema snapshot."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

ROOT = Path(__file__).resolve().parent
SELF = Path(__file__).resolve()
V1 = ROOT / "baseline_native_runtime.py"
V1_SHA256 = "5130bc037e0700f8d498c40ca790aaf248e986189818ae059934ee6488bbfbcd"
V5 = ROOT / "baseline_native_runtime_v5.py"
V5_SHA256 = "f6df1406e0bf821e7512ce1b746492b93ab93f794201432db2c73654bbef59e4"
V1_SNAPSHOT = ROOT / "baseline_runtime_data_snapshot_v4.py"
V1_SNAPSHOT_SHA256 = "7bc63e52688d7b0f4546fe3d8681b7e446ea5b6ddc2c20c7ae6f05c6a0199513"
V5_SNAPSHOT = ROOT / "baseline_runtime_data_snapshot.py"
V5_SNAPSHOT_SHA256 = "eb068749b2483d4b8ca480e5e57865692b89518fe924848f57d324574d167b0c"
SCORING_PARITY = ROOT / "baseline_composite_analysis_v5.py"
SCORING_PARITY_SHA256 = "e57339760921ea77df14d05eda64ed378fee55382185eba0f2de9471a7e04051"


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _canonical(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")


def _need(value: bool, message: str) -> None:
    if not value:
        raise ValueError(message)


def _read(path: Path | str, expected: str, label: str) -> tuple[Path, bytes]:
    checked = Path(path).resolve()
    raw = checked.read_bytes()
    _need(_sha(raw) == expected, f"{label} hash drift")
    return checked, raw


def _load(path: Path, expected: str, label: str) -> tuple[ModuleType, bytes]:
    checked, raw = _read(path, expected, label)
    spec = importlib.util.spec_from_file_location(f"_baseline_runtime_data_scoring_{label}", checked)
    _need(spec is not None and spec.loader is not None, f"{label} cannot load")
    previous = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = previous
    _need(checked.read_bytes() == raw, f"{label} changed while loading")
    return module, raw


def _provided_loader(module: ModuleType, path: Path, expected: str, label: str) -> bytes:
    _need(isinstance(module, ModuleType), f"{label} differs")
    source = getattr(module, "__file__", None)
    _need(type(source) is str and Path(source).resolve() == path.resolve(), f"{label} differs")
    _checked, raw = _read(path, expected, label)
    _need(callable(getattr(module, "load_runtime", None)), f"{label} differs")
    return raw


def _sources(runtime: Any, captured: dict[Path, bytes], label: str) -> None:
    provenance = getattr(runtime, "provenance", None)
    values = provenance.get("source_sha256") if isinstance(provenance, dict) else None
    _need(isinstance(values, dict) and values, f"{label} source provenance differs")
    for source, expected in values.items():
        _need(type(source) is str and type(expected) is str and len(expected) == 64, f"{label} source provenance differs")
        path, raw = _read(Path(source), expected, f"{label} source")
        captured[path] = raw


def _unchanged(captured: dict[Path, bytes]) -> None:
    if any(path.read_bytes() != raw for path, raw in captured.items()):
        raise ValueError("Scoring runtime source or data changed during parity")


def runtime_parity_with_data(
    v1_loader: ModuleType,
    v5_loader: ModuleType,
    *,
    scoring_manifest_path: Path | str,
    expected_scoring_manifest_sha256: str,
    v5_runtime_manifest_path: Path | str,
    expected_v5_runtime_manifest_sha256: str,
    v5_runtime_package_root: Path | str,
    expected_v5_runtime_package_manifest_sha256: str,
    snapshot_manifest_path: Path | str,
    expected_snapshot_manifest_sha256: str,
) -> tuple[dict[str, Any], dict[Path, bytes]]:
    """Run the frozen parity probes using constructors that bind historical data."""
    self_path, self_raw = _read(SELF, _sha(SELF.read_bytes()), "runtime data scoring adapter")
    v1_raw = _provided_loader(v1_loader, V1, V1_SHA256, "v1 scoring runtime loader")
    v5_raw = _provided_loader(v5_loader, V5, V5_SHA256, "v5 scoring runtime loader")
    v1_snapshot, v1_snapshot_raw = _load(V1_SNAPSHOT, V1_SNAPSHOT_SHA256, "v1 snapshot constructor")
    v5_snapshot, v5_snapshot_raw = _load(V5_SNAPSHOT, V5_SNAPSHOT_SHA256, "v5 snapshot constructor")
    scoring, scoring_raw = _load(SCORING_PARITY, SCORING_PARITY_SHA256, "frozen scoring parity")
    _need(callable(getattr(scoring, "_scoring_parity", None)), "frozen scoring parity differs")
    v1_path, v1_manifest_raw = _read(scoring_manifest_path, expected_scoring_manifest_sha256, "v1 scoring manifest")
    v5_path, v5_manifest_raw = _read(v5_runtime_manifest_path, expected_v5_runtime_manifest_sha256, "v5 scoring manifest")
    package_path, package_raw = _read(Path(v5_runtime_package_root) / "candidate-manifest.json", expected_v5_runtime_package_manifest_sha256, "v5 scoring package manifest")
    snapshot_path, snapshot_manifest_raw = _read(snapshot_manifest_path, expected_snapshot_manifest_sha256, "runtime data snapshot manifest")
    snapshot_manifest_storage, _snapshot_manifest, snapshot_raw, snapshot_storage, historical_schema_raw, canonical_path, canonical_raw = v5_snapshot._snapshot(snapshot_path, expected_snapshot_manifest_sha256)
    _need(snapshot_manifest_storage == snapshot_path and snapshot_raw == snapshot_manifest_raw, "runtime data snapshot manifest differs")
    v1_epoch = {
        "old_runtime_loader": {"path": str(V1), "sha256": V1_SHA256},
        "old_runtime_manifest": {"path": str(v1_path), "sha256": expected_scoring_manifest_sha256},
    }
    v5_epoch = {
        "runtime_loader": {"path": str(V5), "sha256": V5_SHA256},
        "runtime_manifest": {"path": str(v5_path), "sha256": expected_v5_runtime_manifest_sha256},
        "runtime_package": {"root": str(Path(v5_runtime_package_root).resolve()), "manifest_sha256": expected_v5_runtime_package_manifest_sha256},
    }
    v1 = v1_snapshot.load_old_runtime_from_epoch(v1_epoch, snapshot_manifest_path=snapshot_path, expected_snapshot_manifest_sha256=expected_snapshot_manifest_sha256)
    v5 = v5_snapshot.load_runtime_from_epoch(v5_epoch, snapshot_manifest_path=snapshot_path, expected_snapshot_manifest_sha256=expected_snapshot_manifest_sha256)
    captured = {
        self_path: self_raw,
        V1.resolve(): v1_raw,
        V5.resolve(): v5_raw,
        V1_SNAPSHOT.resolve(): v1_snapshot_raw,
        V5_SNAPSHOT.resolve(): v5_snapshot_raw,
        SCORING_PARITY.resolve(): scoring_raw,
        v1_path: v1_manifest_raw,
        v5_path: v5_manifest_raw,
        package_path: package_raw,
        snapshot_path: snapshot_manifest_raw,
        snapshot_storage: historical_schema_raw,
        canonical_path: canonical_raw,
    }
    _sources(v1, captured, "v1 scoring runtime")
    _sources(v5, captured, "v5 scoring runtime")
    parity = scoring._scoring_parity(v1, v5)
    _need(isinstance(parity, dict) and parity.get("evidence_class") == "v1_v5_source_bound_scoring_parity", "frozen scoring parity result differs")
    v1.verify()
    v5.verify()
    _unchanged(captured)
    runtime_data_provenance = {
        "schema_version": 1,
        "evidence_class": "v1_v5_scoring_parity_with_explicit_historical_schema_snapshot",
        "snapshot_manifest": {"path": str(snapshot_path), "sha256": expected_snapshot_manifest_sha256, "bytes": len(snapshot_manifest_raw)},
        "historical_schema": {"path": str(snapshot_storage), "sha256": _sha(historical_schema_raw), "bytes": len(historical_schema_raw), "logical_path": v5_snapshot.LOGICAL_SCHEMA},
        "current_canonical_schema": {"path": str(canonical_path), "sha256": _sha(canonical_raw), "preserved": True},
        "v1": {
            "manifest": {"path": str(v1_path), "sha256": expected_scoring_manifest_sha256, "bytes": len(v1_manifest_raw)},
            "runtime_loader": {"path": str(V1), "sha256": V1_SHA256},
            "snapshot_constructor": {"path": str(V1_SNAPSHOT), "sha256": V1_SNAPSHOT_SHA256, "identity": "v4_snapshot_constructor_reused_for_original_v1_scoring_loader"},
        },
        "v5": {
            "manifest": {"path": str(v5_path), "sha256": expected_v5_runtime_manifest_sha256, "bytes": len(v5_manifest_raw)},
            "package_manifest": {"path": str(package_path), "sha256": expected_v5_runtime_package_manifest_sha256, "bytes": len(package_raw)},
            "runtime_loader": {"path": str(V5), "sha256": V5_SHA256},
            "snapshot_constructor": {"path": str(V5_SNAPSHOT), "sha256": V5_SNAPSHOT_SHA256},
        },
    }
    return ({
        "v1_manifest": {"sha256": expected_scoring_manifest_sha256, "bytes": len(v1_manifest_raw)},
        "v5_manifest": {"sha256": expected_v5_runtime_manifest_sha256, "bytes": len(v5_manifest_raw)},
        "v5_package_manifest": {"sha256": expected_v5_runtime_package_manifest_sha256, "bytes": len(package_raw)},
        "parity": parity,
        "commitment_sha256": _sha(_canonical(parity)),
        "runtime_data_provenance": runtime_data_provenance,
    }, captured)
