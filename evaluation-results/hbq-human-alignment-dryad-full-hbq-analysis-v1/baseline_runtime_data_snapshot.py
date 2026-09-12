"""Provider-free V5 runtime loading with an explicit immutable schema snapshot."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

ROOT = Path(__file__).resolve().parent
REPOSITORY = ROOT.parents[1]
SELF = Path(__file__).resolve()
V5 = ROOT / "baseline_native_runtime_v5.py"
V5_SHA256 = "f6df1406e0bf821e7512ce1b746492b93ab93f794201432db2c73654bbef59e4"
LOGICAL_SCHEMA = "schema/hbq_judge_response.schema.json"
OLD_SCHEMA_SHA256 = "49c7d824ba5dd957e67968ba3ae6ceb8a7ed9434dfb0dfc654836a76613c7854"
CURRENT_SCHEMA_SHA256 = "8896aabcd8f8a503f171d95d70117535da22ceff90400ff8698ee8b3f607edd8"


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _need(value: bool, message: str) -> None:
    if not value:
        raise ValueError(message)


def _v5() -> ModuleType:
    raw = V5.read_bytes()
    _need(_sha(raw) == V5_SHA256, "V5 runtime loader differs")
    spec = importlib.util.spec_from_file_location("_baseline_runtime_data_snapshot_v5", V5)
    _need(spec is not None and spec.loader is not None, "V5 runtime loader cannot load")
    previous = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = previous
    _need(V5.read_bytes() == raw, "V5 runtime loader changed while loading")
    return module


def _object(raw: bytes, label: str) -> dict[str, Any]:
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"{label} malformed") from error
    _need(isinstance(value, dict), f"{label} object")
    return value


def _snapshot(path: Path, expected: str) -> tuple[Path, dict[str, Any], bytes, Path, bytes, Path, bytes]:
    manifest_path = Path(path).resolve()
    try:
        raw = manifest_path.read_bytes()
    except OSError as error:
        raise ValueError("runtime data snapshot manifest missing") from error
    _need(_sha(raw) == expected, "runtime data snapshot manifest differs")
    value = _object(raw, "runtime data snapshot manifest")
    required = {"schema_version", "kind", "created_at", "source_git_path", "source_git_revision", "git_blob_sha256", "snapshot", "current_canonical_schema", "transformation", "old_evidence_modified", "source_snapshot_loader_approved", "provider_calls_made"}
    _need(set(value) == required and value.get("schema_version") == 1 and value.get("kind") == "inert_byte_exact_historical_schema_snapshot" and value.get("source_git_path") == LOGICAL_SCHEMA and value.get("git_blob_sha256") == OLD_SCHEMA_SHA256 and value.get("transformation") == "none" and value.get("old_evidence_modified") is False and value.get("source_snapshot_loader_approved") is False and value.get("provider_calls_made") == 0, "runtime data snapshot manifest schema differs")
    snapshot = value.get("snapshot")
    canonical = value.get("current_canonical_schema")
    _need(isinstance(snapshot, dict) and isinstance(canonical, dict) and set(snapshot) == {"path", "bytes", "sha256"} and set(canonical) == {"path", "sha256", "preserved"} and snapshot.get("sha256") == OLD_SCHEMA_SHA256 and canonical.get("sha256") == CURRENT_SCHEMA_SHA256 and canonical.get("preserved") is True, "runtime data snapshot bindings differ")
    storage = Path(snapshot["path"]).resolve()
    canonical_path = Path(canonical["path"]).resolve()
    try:
        snapshot_raw = storage.read_bytes()
        canonical_raw = canonical_path.read_bytes()
    except OSError as error:
        raise ValueError("runtime data snapshot storage missing") from error
    _need(len(snapshot_raw) == snapshot["bytes"] and _sha(snapshot_raw) == snapshot["sha256"] and canonical_path == (REPOSITORY / LOGICAL_SCHEMA).resolve() and _sha(canonical_raw) == canonical["sha256"], "runtime data snapshot bytes differ")
    return manifest_path, value, raw, storage, snapshot_raw, canonical_path, canonical_raw


def _data_reader(*, bindings: dict[Path, bytes], original: Any) -> Any:
    def load_data(path: str | Path) -> Any:
        candidate = Path(path).resolve()
        if candidate in bindings:
            return json.loads(bindings[candidate].decode("utf-8"))
        return original(path)
    return load_data


def load_runtime_from_epoch(epoch: dict[str, Any], *, snapshot_manifest_path: Path, expected_snapshot_manifest_sha256: str) -> Any:
    """Load the V5 code bindings while resolving only the historical schema from a snapshot."""
    _need(isinstance(epoch, dict), "runtime epoch differs")
    loader, manifest_descriptor, package = epoch.get("runtime_loader"), epoch.get("runtime_manifest"), epoch.get("runtime_package")
    _need(isinstance(loader, dict) and isinstance(manifest_descriptor, dict) and isinstance(package, dict) and loader.get("path") == str(V5), "runtime epoch V5 loader differs")
    _need(loader.get("sha256") == V5_SHA256 and isinstance(manifest_descriptor.get("path"), str) and isinstance(manifest_descriptor.get("sha256"), str) and isinstance(package.get("root"), str) and isinstance(package.get("manifest_sha256"), str), "runtime epoch bindings differ")
    self_raw = SELF.read_bytes()
    snapshot_manifest_storage, _snapshot_manifest, snapshot_manifest_raw, snapshot_storage, snapshot_raw, canonical_path, canonical_raw = _snapshot(Path(snapshot_manifest_path), expected_snapshot_manifest_sha256)
    v5_raw = V5.read_bytes()
    v5 = _v5()
    helper, helper_raw = v5._helper()
    captures: dict[Path, bytes] = {helper._plain(v5.HELPER): helper_raw}
    runtime_manifest_raw = helper._read(Path(manifest_descriptor["path"]), manifest_descriptor["sha256"], captures)
    runtime_manifest = v5._manifest(runtime_manifest_raw)
    _need(runtime_manifest["runtime_package_manifest_sha256"] == package["manifest_sha256"], "runtime package manifest anchor differs")
    package_root = helper._plain(Path(package["root"]), file=False)
    records, inventory = v5._capture_package(helper, package_root, package["manifest_sha256"], captures)
    storage = v5._package_storage(helper, package_root, records, runtime_manifest["shared_runtime_bindings"])
    parent_raw = helper._read(v5.PARENT_RUNTIME_MANIFEST, v5.PARENT_RUNTIME_MANIFEST_SHA256, captures)
    v5._parent_manifest(parent_raw)
    helper._read(v5.PARENT_RUNTIME_LOADER, v5.PARENT_RUNTIME_LOADER_SHA256, captures)
    protocol = v5._object(helper._read(v5.PROTOCOL, v5.PROTOCOL_SHA256, captures), "Protocol")
    native, native_raw = helper._native()
    captures[helper._plain(helper.NATIVE)] = native_raw
    runtime_bindings = protocol.get("runtime_bindings")
    supplementary = getattr(native, "SUPPLEMENTARY_PINS", None)
    _need(isinstance(runtime_bindings, dict) and isinstance(supplementary, dict) and runtime_bindings.get(LOGICAL_SCHEMA) == OLD_SCHEMA_SHA256, "runtime schema pin differs")
    for relative, expected in {**runtime_bindings, **supplementary}.items():
        if relative == LOGICAL_SCHEMA:
            continue
        helper._read(REPOSITORY / relative, expected, captures)
    for relative, expected in runtime_manifest["helper_source_bindings"].items():
        helper._read(REPOSITORY / relative, expected, captures)
    helper._read(REPOSITORY / runtime_manifest["bridge_path"], runtime_manifest["bridge_sha256"], captures)
    hbq = native._private_modules(REPOSITORY / "src/hbqrs", ("core", "paths", "weights", "runner", "grok_broker_transport", "grok_broker_transport_v2", "grok_broker_transport_v3"), captures)
    shared = helper._shared_modules(storage, captures)
    logical_path = (REPOSITORY / LOGICAL_SCHEMA).resolve()
    verdict_path = (REPOSITORY / "schema/hbq_verdict.schema.json").resolve()
    weight_path = (REPOSITORY / "schema/hbq_weight_profile.schema.json").resolve()
    data_bindings = {logical_path: snapshot_raw, verdict_path: captures[verdict_path], weight_path: captures[weight_path]}
    snapshot_load = _data_reader(bindings=data_bindings, original=hbq["core"].load_data)
    hbq["core"].load_data = snapshot_load
    hbq["runner"].load_data = snapshot_load
    original_record = hbq["runner"]._read_text_record
    def read_text_record(path: Path) -> dict[str, Any]:
        candidate = Path(path).resolve()
        if candidate != logical_path:
            return original_record(path)
        return {"path": str(snapshot_storage), "name": snapshot_storage.name, "bytes": len(snapshot_raw), "sha256": _sha(snapshot_raw), "text": snapshot_raw.decode("utf-8-sig")}
    hbq["runner"]._read_text_record = read_text_record
    _need(hbq["paths"].book_root().resolve() == REPOSITORY.resolve(), "baseline runtime book root differs")
    core = hbq["core"]
    modules = core.load_modules(REPOSITORY / "registry/all_modules.json")
    bundle = core.resolve_bundle(core.load_bundles(REPOSITORY / "bundles/all_bundles.json"), "prose.short_story")
    compiled = core.compile_bundle(modules, bundle)
    order = {"hard_gate": 0, "domain": 1, "penalty": 2, "supplemental": 3}
    questions = sorted(core.compiled_questions(compiled), key=lambda item: order[item["role"]])
    _need(len(questions) == 178 and hbq["runner"]._response_schema() == json.loads(snapshot_raw.decode("utf-8")), "baseline runtime schema resolution differs")
    schema_pins = [
        {"logical_path": LOGICAL_SCHEMA, "storage_path": str(snapshot_storage), "bytes": len(snapshot_raw), "sha256": OLD_SCHEMA_SHA256, "origin": "protocol_runtime_binding"},
        {"logical_path": "schema/hbq_verdict.schema.json", "storage_path": str(verdict_path), "bytes": len(data_bindings[verdict_path]), "sha256": _sha(data_bindings[verdict_path]), "origin": "native_supplementary_pin"},
        {"logical_path": "schema/hbq_weight_profile.schema.json", "storage_path": str(weight_path), "bytes": len(data_bindings[weight_path]), "sha256": _sha(data_bindings[weight_path]), "origin": "native_supplementary_pin"},
    ]
    def verify() -> None:
        current = v5._package_inventory(helper, package_root)
        _need(set(current) == set(inventory), "candidate runtime package changed during operation")
        _need(all(helper._plain(path).read_bytes() == data for path, data in captures.items()), "baseline runtime source changed during operation")
        try:
            current_snapshot = snapshot_storage.read_bytes()
            current_canonical = canonical_path.read_bytes()
            current_snapshot_manifest = snapshot_manifest_storage.read_bytes()
            current_loader = SELF.read_bytes()
            current_v5 = V5.read_bytes()
        except OSError as error:
            raise ValueError("runtime data missing during operation") from error
        _need(current_snapshot == snapshot_raw and current_canonical == canonical_raw, "runtime data changed during operation")
        _need(current_snapshot_manifest == snapshot_manifest_raw, "runtime data snapshot manifest changed during operation")
        _need(current_loader == self_raw and current_v5 == v5_raw, "runtime loader source changed during operation")
    verify()
    return SimpleNamespace(core=core, runner=hbq["runner"], weights=hbq["weights"], broker=shared["broker"], adapter=shared["adapters.grok_exec"], transport=hbq["grok_broker_transport_v3"], transport_sha256=runtime_manifest["bridge_sha256"], modules=modules, bundle=bundle, compiled=compiled, questions=questions, response_schema_mode="batch_question_ids_v1", verify=verify, provenance={"evidence_class": "prospective_v5_runtime_with_explicit_historical_data_snapshot", "code": {"runtime_loader": {"path": str(SELF), "sha256": _sha(self_raw)}, "historical_helpers": {"v5_runtime_loader": {"path": str(V5), "sha256": V5_SHA256}}, "manifest_sha256": manifest_descriptor["sha256"], "runtime_package_manifest_sha256": package["manifest_sha256"]}, "data": {"snapshot_manifest": {"path": str(snapshot_manifest_storage), "sha256": expected_snapshot_manifest_sha256}, "schema_pins": schema_pins, "current_canonical_schema": {"path": str(canonical_path), "sha256": _sha(canonical_raw), "preserved": True}}, "source_sha256": {str(path): _sha(data) for path, data in captures.items()}, "provider_calls": 0, "native_admission": False, "execution_authority": False})
