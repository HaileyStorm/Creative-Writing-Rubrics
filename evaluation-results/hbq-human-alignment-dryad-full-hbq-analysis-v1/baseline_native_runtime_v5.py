"""Load a frozen v5 source package without granting execution authority."""

from __future__ import annotations

import hashlib
import json
import re
import stat
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

ROOT = Path(__file__).resolve().parent
REPOSITORY = ROOT.parents[1]
HELPER = ROOT / "historical_replay_runtime.py"
HELPER_SHA256 = "d98686761c4af296c4132a477bc54c3bcdfc3bb8b0140ffd2681919652fe81f9"
PROTOCOL = ROOT / "protocol-v2.json"
PROTOCOL_SHA256 = "33e7dde670bf212da0ee7c4cd6cf628f9a43949dc597cea47b0d97aa4e158e2b"
PARENT_RUNTIME_MANIFEST = ROOT / "baseline-runtime-v1.json"
PARENT_RUNTIME_MANIFEST_SHA256 = "3b1f70a40a6dac8028d11c52f747400ab88dff3a193f828e3940c53813f3273d"
PARENT_RUNTIME_LOADER = ROOT / "baseline_native_runtime.py"
PARENT_RUNTIME_LOADER_SHA256 = "5130bc037e0700f8d498c40ca790aaf248e986189818ae059934ee6488bbfbcd"
PLAN_SHA256 = "edeadb93c485ba227153329b5ae420de1c9d08d95e920bac0635d197fd3dbd7f"
BRIDGE = "src/hbqrs/grok_broker_transport_v3.py"
V1_BRIDGE = "src/hbqrs/grok_broker_transport.py"
V1_BRIDGE_SHA256 = "cd349c9b512a3524f6bd0f9787035af618754f2b06363dc2e9aceda7e72305be"
V2_BRIDGE = "src/hbqrs/grok_broker_transport_v2.py"
V2_BRIDGE_SHA256 = "da9698e23aee9eb4fc0daaa76b9d32dfc0090462ad6fede587b865caa363eaa5"
NONVISUAL_TRANSPORT_CONTRACT_SHA256 = "08459d7354518e3d8fbf0bc27b2c8308ef4414b2a85550ea18941c7f918ec91b"
SHARED_PATHS = frozenset({
    "prepare_grok_evidence.py", "broker.py", "adapters/grok_exec.py",
    "adapters/json_schema_subset.py", "image_canary.py", "grok_usage_evidence.py",
})
_HASH = re.compile(r"[0-9a-f]{64}\Z")
_SAFE_MEMBER = re.compile(r"[A-Za-z0-9_][A-Za-z0-9._-]*(?:/[A-Za-z0-9_][A-Za-z0-9._-]*)*\Z")


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _object(raw: bytes, label: str) -> dict[str, Any]:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        value: dict[str, Any] = {}
        for key, item in items:
            require(key not in value, f"{label} has duplicate keys")
            value[key] = item
        return value

    try:
        value = json.loads(
            raw.decode("utf-8"), object_pairs_hook=pairs,
            parse_constant=lambda _: (_ for _ in ()).throw(ValueError("nonfinite")),
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise ValueError(f"{label} is malformed") from error
    require(isinstance(value, dict), f"{label} must be an object")
    return value


def _helper() -> tuple[ModuleType, bytes]:
    for path in (HELPER, *HELPER.parents):
        info = path.lstat()
        require(
            not stat.S_ISLNK(info.st_mode) and not getattr(info, "st_file_attributes", 0) & 0x400,
            "Runtime helper path contains a link or reparse point",
        )
    raw = HELPER.read_bytes()
    require(digest(raw) == HELPER_SHA256, "Runtime helper source differs")
    helper = ModuleType("_dryad_baseline_runtime_v5_helper")
    helper.__file__ = str(HELPER)
    exec(compile(raw, str(HELPER), "exec"), helper.__dict__)  # noqa: S102 - exact hash-pinned helper definitions.
    require(helper._plain(HELPER).read_bytes() == raw, "Runtime helper changed while loading")
    return helper, raw


def _manifest(raw: bytes) -> dict[str, Any]:
    value = _object(raw, "Runtime manifest")
    expected = {
        "schema_version", "evidence_class", "baseline_plan_sha256", "parent_protocol_sha256",
        "bridge_path", "bridge_sha256", "shared_runtime_bindings",
        "parent_runtime_manifest_sha256", "parent_runtime_loader_sha256",
        "runtime_package_manifest_sha256", "helper_source_bindings", "adapter_version",
        "execution_policy", "tools", "identity_evidence", "reasoning_attested",
        "nonvisual_transport_contract_sha256",
    }
    require(
        set(value) == expected and type(value["schema_version"]) is int
        and value["schema_version"] == 2
        and value["evidence_class"] == "baseline_runtime_source_bindings_v5",
        "Runtime manifest schema differs",
    )
    require(
        value["baseline_plan_sha256"] == PLAN_SHA256
        and value["parent_protocol_sha256"] == PROTOCOL_SHA256
        and value["parent_runtime_manifest_sha256"] == PARENT_RUNTIME_MANIFEST_SHA256
        and value["parent_runtime_loader_sha256"] == PARENT_RUNTIME_LOADER_SHA256,
        "Runtime manifest parent binding differs",
    )
    require(
        value["bridge_path"] == BRIDGE
        and type(value["adapter_version"]) is int and value["adapter_version"] == 5
        and value["execution_policy"] == "bounded_nonvisual_deny_wins_attested"
        and value["tools"] == "deny_wins_none_attested"
        and value["identity_evidence"] == "requested_only"
        and value["reasoning_attested"] is False
        and value["nonvisual_transport_contract_sha256"] == NONVISUAL_TRANSPORT_CONTRACT_SHA256,
        "Runtime manifest execution contract differs",
    )
    shared = value["shared_runtime_bindings"]
    helper = value["helper_source_bindings"]
    require(
        isinstance(shared, dict) and set(shared) == SHARED_PATHS
        and isinstance(helper, dict)
        and helper == {V1_BRIDGE: V1_BRIDGE_SHA256, V2_BRIDGE: V2_BRIDGE_SHA256},
        "Runtime manifest source bindings differ",
    )
    hashes = [value["bridge_sha256"], value["runtime_package_manifest_sha256"], *shared.values()]
    require(all(isinstance(item, str) and _HASH.fullmatch(item) for item in hashes), "Runtime manifest hash differs")
    return value


def _parent_manifest(raw: bytes) -> dict[str, Any]:
    value = _object(raw, "Parent runtime manifest")
    expected = {
        "schema_version", "evidence_class", "baseline_plan_sha256", "parent_protocol_sha256",
        "bridge_path", "bridge_sha256", "shared_runtime_bindings", "adapter_version",
        "execution_policy", "tools",
    }
    require(
        set(value) == expected and value["schema_version"] == 1
        and value["evidence_class"] == "baseline_runtime_source_bindings"
        and value["baseline_plan_sha256"] == PLAN_SHA256
        and value["parent_protocol_sha256"] == PROTOCOL_SHA256
        and value["bridge_path"] == V2_BRIDGE
        and value["bridge_sha256"] == V2_BRIDGE_SHA256
        and value["adapter_version"] == 4
        and value["execution_policy"] == "bounded_nonvisual_deny_wins_attested"
        and value["tools"] == "deny_wins_none_attested",
        "Parent runtime manifest differs",
    )
    return value


def _member_path(helper: ModuleType, root: Path, relative: str) -> Path:
    require(
        type(relative) is str and _SAFE_MEMBER.fullmatch(relative) is not None,
        "Candidate runtime member path differs",
    )
    path = helper._plain(root.joinpath(*relative.split("/")))
    require(path.relative_to(root).as_posix() == relative, "Candidate runtime member path escapes package")
    return path


def _package_inventory(helper: ModuleType, root: Path) -> dict[str, Path]:
    inventory: dict[str, Path] = {}
    for path in root.rglob("*"):
        info = path.lstat()
        require(
            not stat.S_ISLNK(info.st_mode) and not getattr(info, "st_file_attributes", 0) & 0x400,
            "Candidate runtime package contains a link or reparse point",
        )
        if path.is_dir():
            helper._plain(path, file=False)
            continue
        require(path.is_file(), "Candidate runtime package contains a non-file member")
        checked = helper._plain(path)
        relative = checked.relative_to(root).as_posix()
        require(_SAFE_MEMBER.fullmatch(relative) is not None, "Candidate runtime member path differs")
        require(relative not in inventory, "Candidate runtime package contains duplicate member paths")
        inventory[relative] = checked
    return inventory


def _package_manifest(raw: bytes) -> dict[str, dict[str, Any]]:
    value = _object(raw, "Candidate runtime package manifest")
    require(
        set(value) == {"schema_version", "kind", "explicit_exclusion", "files"}
        and value["schema_version"] == 7
        and value["kind"] == "complete_candidate_runtime_probe_set"
        and value["explicit_exclusion"] == ["candidate-manifest.json"]
        and isinstance(value["files"], list) and len(value["files"]) == 30,
        "Candidate runtime package manifest schema differs",
    )
    records: dict[str, dict[str, Any]] = {}
    for record in value["files"]:
        require(isinstance(record, dict) and set(record) == {"path", "bytes", "sha256"}, "Candidate runtime member schema differs")
        relative = record["path"]
        require(
            type(relative) is str and _SAFE_MEMBER.fullmatch(relative) is not None
            and relative != "candidate-manifest.json" and relative not in records
            and type(record["bytes"]) is int and record["bytes"] >= 0
            and isinstance(record["sha256"], str) and _HASH.fullmatch(record["sha256"]) is not None,
            "Candidate runtime member binding differs",
        )
        records[relative] = dict(record)
    return records


def _capture_package(
    helper: ModuleType,
    root: Path,
    expected_sha256: str,
    captures: dict[Path, bytes],
) -> tuple[dict[str, dict[str, Any]], dict[str, Path]]:
    root = helper._plain(root, file=False)
    manifest_path = helper._plain(root / "candidate-manifest.json")
    manifest_raw = helper._read(manifest_path, expected_sha256, captures)
    records = _package_manifest(manifest_raw)
    inventory = _package_inventory(helper, root)
    require(
        set(inventory) == set(records) | {"candidate-manifest.json"},
        "Candidate runtime package inventory differs",
    )
    for relative, record in records.items():
        path = _member_path(helper, root, relative)
        require(path == inventory[relative], "Candidate runtime package member differs")
        raw = helper._read(path, record["sha256"], captures)
        require(len(raw) == record["bytes"], "Candidate runtime package byte binding differs")
    return records, inventory


def _package_storage(
    helper: ModuleType,
    root: Path,
    records: dict[str, dict[str, Any]],
    shared_bindings: dict[str, str],
) -> dict[str, Path]:
    storage: dict[str, Path] = {}
    for relative in SHARED_PATHS:
        member = f"model_work_queue/{relative}"
        record = records.get(member)
        require(
            record is not None and record["sha256"] == shared_bindings[relative],
            "Candidate runtime shared source binding differs",
        )
        storage[relative[:-3].replace("/", ".")] = _member_path(helper, root, member)
    require(
        set(storage) == {
            "prepare_grok_evidence", "broker", "adapters.grok_exec",
            "adapters.json_schema_subset", "image_canary", "grok_usage_evidence",
        },
        "Candidate runtime shared source map differs",
    )
    return storage


def load_runtime(
    manifest_path: Path,
    *,
    expected_manifest_sha256: str,
    runtime_package_root: Path,
    expected_package_manifest_sha256: str,
) -> Any:
    """Load source bytes only; a verified package never arms or contacts a provider."""
    require(
        isinstance(expected_manifest_sha256, str) and _HASH.fullmatch(expected_manifest_sha256) is not None
        and isinstance(expected_package_manifest_sha256, str)
        and _HASH.fullmatch(expected_package_manifest_sha256) is not None,
        "Runtime manifest anchor differs",
    )
    helper, helper_raw = _helper()
    captures: dict[Path, bytes] = {helper._plain(HELPER): helper_raw}
    raw = helper._read(Path(manifest_path), expected_manifest_sha256, captures)
    manifest = _manifest(raw)
    require(
        manifest["runtime_package_manifest_sha256"] == expected_package_manifest_sha256,
        "Runtime package manifest anchor differs",
    )
    package_root = helper._plain(Path(runtime_package_root), file=False)
    records, inventory = _capture_package(
        helper, package_root, expected_package_manifest_sha256, captures,
    )
    storage = _package_storage(helper, package_root, records, manifest["shared_runtime_bindings"])

    parent_raw = helper._read(PARENT_RUNTIME_MANIFEST, PARENT_RUNTIME_MANIFEST_SHA256, captures)
    _parent_manifest(parent_raw)
    helper._read(PARENT_RUNTIME_LOADER, PARENT_RUNTIME_LOADER_SHA256, captures)
    protocol = _object(helper._read(PROTOCOL, PROTOCOL_SHA256, captures), "Protocol")
    native, native_raw = helper._native()
    captures[helper._plain(helper.NATIVE)] = native_raw
    runtime_bindings = protocol.get("runtime_bindings")
    require(
        isinstance(runtime_bindings, dict)
        and all(isinstance(path, str) and isinstance(sha, str) and _HASH.fullmatch(sha) for path, sha in runtime_bindings.items()),
        "Protocol runtime bindings differ",
    )
    supplementary = getattr(native, "SUPPLEMENTARY_PINS", None)
    require(
        isinstance(supplementary, dict)
        and all(isinstance(path, str) and isinstance(sha, str) and _HASH.fullmatch(sha) for path, sha in supplementary.items()),
        "Native supplementary bindings differ",
    )
    for relative, expected in {**runtime_bindings, **supplementary}.items():
        helper._read(REPOSITORY / relative, expected, captures)
    for relative, expected in manifest["helper_source_bindings"].items():
        helper._read(REPOSITORY / relative, expected, captures)
    helper._read(REPOSITORY / manifest["bridge_path"], manifest["bridge_sha256"], captures)

    def verify() -> None:
        current = _package_inventory(helper, package_root)
        require(set(current) == set(inventory), "Candidate runtime package changed during operation")
        require(
            all(helper._plain(path).read_bytes() == data for path, data in captures.items()),
            "Baseline runtime source changed during operation",
        )

    hbq = native._private_modules(
        REPOSITORY / "src/hbqrs",
        ("core", "paths", "weights", "runner", "grok_broker_transport", "grok_broker_transport_v2", "grok_broker_transport_v3"),
        captures,
    )
    shared = helper._shared_modules(storage, captures)
    require(hbq["paths"].book_root().resolve() == REPOSITORY.resolve(), "Baseline runtime book root differs")
    core = hbq["core"]
    modules = core.load_modules(REPOSITORY / "registry/all_modules.json")
    bundle = core.resolve_bundle(core.load_bundles(REPOSITORY / "bundles/all_bundles.json"), "prose.short_story")
    compiled = core.compile_bundle(modules, bundle)
    order = {"hard_gate": 0, "domain": 1, "penalty": 2, "supplemental": 3}
    questions = sorted(core.compiled_questions(compiled), key=lambda item: order[item["role"]])
    require(len(questions) == 178, "Baseline runtime question inventory differs")
    verify()
    return SimpleNamespace(
        core=core, runner=hbq["runner"], weights=hbq["weights"], broker=shared["broker"],
        adapter=shared["adapters.grok_exec"], transport=hbq["grok_broker_transport_v3"],
        transport_sha256=manifest["bridge_sha256"], modules=modules, bundle=bundle,
        compiled=compiled, questions=questions, response_schema_mode="batch_question_ids_v1",
        verify=verify,
        provenance={
            "evidence_class": "prospective_baseline_runtime_source_binding_v5",
            "manifest_sha256": expected_manifest_sha256,
            "runtime_package_manifest_sha256": expected_package_manifest_sha256,
            "source_sha256": {str(path): digest(data) for path, data in captures.items()},
            "provider_calls": 0, "native_admission": False, "execution_authority": False,
        },
    )
