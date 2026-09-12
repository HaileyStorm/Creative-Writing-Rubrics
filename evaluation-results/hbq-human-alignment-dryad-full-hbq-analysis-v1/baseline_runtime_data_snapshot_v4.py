"""Load the frozen V4 runtime with only its historical response schema snapshotted."""
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
V4 = ROOT / "baseline_native_runtime.py"
V4_SHA256 = "5130bc037e0700f8d498c40ca790aaf248e986189818ae059934ee6488bbfbcd"
SNAPSHOT_HELPERS = ROOT / "baseline_runtime_data_snapshot.py"
SNAPSHOT_HELPERS_SHA256 = "eb068749b2483d4b8ca480e5e57865692b89518fe924848f57d324574d167b0c"
LOGICAL_SCHEMA = "schema/hbq_judge_response.schema.json"
OLD_SCHEMA_SHA256 = "49c7d824ba5dd957e67968ba3ae6ceb8a7ed9434dfb0dfc654836a76613c7854"
CURRENT_SCHEMA_SHA256 = "8896aabcd8f8a503f171d95d70117535da22ceff90400ff8698ee8b3f607edd8"


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _need(value: bool, message: str) -> None:
    if not value:
        raise ValueError(message)


def _v4() -> ModuleType:
    raw = V4.read_bytes()
    _need(_sha(raw) == V4_SHA256, "V4 runtime loader differs")
    spec = importlib.util.spec_from_file_location("_baseline_runtime_data_snapshot_v4", V4)
    _need(spec is not None and spec.loader is not None, "V4 runtime loader cannot load")
    previous = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = previous
    _need(V4.read_bytes() == raw, "V4 runtime loader changed while loading")
    return module


def _snapshot_helpers() -> tuple[ModuleType, bytes]:
    raw = SNAPSHOT_HELPERS.read_bytes()
    _need(_sha(raw) == SNAPSHOT_HELPERS_SHA256, "snapshot helper source differs")
    spec = importlib.util.spec_from_file_location("_baseline_runtime_data_snapshot_helpers", SNAPSHOT_HELPERS)
    _need(spec is not None and spec.loader is not None, "snapshot helpers cannot load")
    previous = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = previous
    _need(SNAPSHOT_HELPERS.read_bytes() == raw, "snapshot helper source changed while loading")
    return module, raw


def _snapshot(path: Path, expected: str) -> tuple[Path, dict[str, Any], bytes, Path, bytes, Path, bytes]:
    helpers, _ = _snapshot_helpers()
    return helpers._snapshot(path, expected)


def load_old_runtime_from_epoch(
    epoch: dict[str, Any], *, snapshot_manifest_path: Path, expected_snapshot_manifest_sha256: str,
) -> Any:
    """Construct the pinned V4 namespace; construction is not native admission."""
    _need(isinstance(epoch, dict), "runtime epoch differs")
    loader = epoch.get("old_runtime_loader")
    manifest_descriptor = epoch.get("old_runtime_manifest")
    _need(
        isinstance(loader, dict) and isinstance(manifest_descriptor, dict)
        and loader.get("path") == str(V4) and loader.get("sha256") == V4_SHA256
        and isinstance(manifest_descriptor.get("path"), str)
        and isinstance(manifest_descriptor.get("sha256"), str),
        "runtime epoch V4 bindings differ",
    )
    self_raw = SELF.read_bytes()
    snapshot_helpers, snapshot_helpers_raw = _snapshot_helpers()
    snapshot_manifest_storage, _snapshot_manifest, snapshot_manifest_raw, snapshot_storage, snapshot_raw, canonical_path, canonical_raw = snapshot_helpers._snapshot(
        Path(snapshot_manifest_path), expected_snapshot_manifest_sha256,
    )
    v4_raw = V4.read_bytes()
    v4 = _v4()
    helper, helper_raw = v4._loader()
    captures: dict[Path, bytes] = {helper._plain(v4.LOADER): helper_raw}
    runtime_manifest_raw = helper._read(
        Path(manifest_descriptor["path"]), manifest_descriptor["sha256"], captures,
    )
    runtime_manifest = v4._manifest(runtime_manifest_raw)
    protocol = helper._json(helper._read(v4.PROTOCOL, v4.PROTOCOL_SHA256, captures), "Protocol")
    native, native_raw = helper._native()
    captures[helper._plain(helper.NATIVE)] = native_raw
    runtime_bindings = protocol.get("runtime_bindings")
    supplementary = getattr(native, "SUPPLEMENTARY_PINS", None)
    _need(
        isinstance(runtime_bindings, dict) and isinstance(supplementary, dict)
        and runtime_bindings.get(LOGICAL_SCHEMA) == OLD_SCHEMA_SHA256,
        "runtime schema pin differs",
    )
    for relative, expected in {**runtime_bindings, **supplementary}.items():
        if relative != LOGICAL_SCHEMA:
            helper._read(REPOSITORY / relative, expected, captures)
    helper._read(REPOSITORY / v4.BRIDGE, runtime_manifest["bridge_sha256"], captures)
    storage: dict[str, Path] = {}
    for relative, expected in runtime_manifest["shared_runtime_bindings"].items():
        path = v4.SHARED / relative
        helper._read(path, expected, captures)
        storage[relative[:-3].replace("/", ".")] = helper._plain(path)

    hbq = native._private_modules(
        REPOSITORY / "src/hbqrs",
        ("core", "paths", "weights", "runner", "grok_broker_transport", "grok_broker_transport_v2"),
        captures,
    )
    shared = helper._shared_modules(storage, captures)
    logical_path = (REPOSITORY / LOGICAL_SCHEMA).resolve()
    verdict_path = (REPOSITORY / "schema/hbq_verdict.schema.json").resolve()
    weight_path = (REPOSITORY / "schema/hbq_weight_profile.schema.json").resolve()
    data_bindings = {
        logical_path: snapshot_raw,
        verdict_path: captures[verdict_path],
        weight_path: captures[weight_path],
    }
    snapshot_load = snapshot_helpers._data_reader(bindings=data_bindings, original=hbq["core"].load_data)
    hbq["core"].load_data = snapshot_load
    hbq["runner"].load_data = snapshot_load
    original_record = hbq["runner"]._read_text_record

    def read_text_record(path: Path) -> dict[str, Any]:
        candidate = Path(path).resolve()
        if candidate != logical_path:
            return original_record(path)
        return {
            "path": str(snapshot_storage), "name": snapshot_storage.name,
            "bytes": len(snapshot_raw), "sha256": _sha(snapshot_raw),
            "text": snapshot_raw.decode("utf-8-sig"),
        }

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
        _need(all(helper._plain(path).read_bytes() == data for path, data in captures.items()), "baseline runtime source changed during operation")
        try:
            current_snapshot = snapshot_storage.read_bytes()
            current_canonical = canonical_path.read_bytes()
            current_snapshot_manifest = snapshot_manifest_storage.read_bytes()
            current_loader = SELF.read_bytes()
            current_v4 = V4.read_bytes()
            current_snapshot_helpers = SNAPSHOT_HELPERS.read_bytes()
        except OSError as error:
            raise ValueError("runtime data missing during operation") from error
        _need(current_snapshot == snapshot_raw and current_canonical == canonical_raw, "runtime data changed during operation")
        _need(current_snapshot_manifest == snapshot_manifest_raw, "runtime data snapshot manifest changed during operation")
        _need(current_loader == self_raw and current_v4 == v4_raw and current_snapshot_helpers == snapshot_helpers_raw, "runtime loader source changed during operation")

    verify()
    return SimpleNamespace(
        core=core, runner=hbq["runner"], weights=hbq["weights"], broker=shared["broker"],
        adapter=shared["adapters.grok_exec"], transport=hbq["grok_broker_transport_v2"],
        transport_sha256=runtime_manifest["bridge_sha256"], modules=modules, bundle=bundle,
        compiled=compiled, questions=questions, response_schema_mode="batch_question_ids_v1", verify=verify,
        provenance={
            "evidence_class": "constructor_verified_v4_runtime_with_explicit_historical_data_snapshot",
            "code": {
                "runtime_loader": {"path": str(SELF), "sha256": _sha(self_raw)},
                "historical_v4_runtime_loader": {"path": str(V4), "sha256": V4_SHA256},
                "frozen_snapshot_helpers": {"path": str(SNAPSHOT_HELPERS), "sha256": SNAPSHOT_HELPERS_SHA256},
                "historical_helper": {"path": str(v4.LOADER), "sha256": v4.LOADER_SHA256},
                "manifest_sha256": manifest_descriptor["sha256"],
            },
            "data": {
                "snapshot_manifest": {"path": str(snapshot_manifest_storage), "sha256": expected_snapshot_manifest_sha256},
                "schema_pins": schema_pins,
                "current_canonical_schema": {"path": str(canonical_path), "sha256": _sha(canonical_raw), "preserved": True},
            },
            "source_sha256": {str(path): _sha(data) for path, data in captures.items()},
            "provider_calls": 0, "native_admission": False, "execution_authority": False,
        },
    )
