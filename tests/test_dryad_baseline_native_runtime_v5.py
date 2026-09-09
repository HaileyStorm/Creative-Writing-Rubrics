"""Synthetic package checks for the source-only Dryad v5 runtime loader."""

from __future__ import annotations

import builtins
import hashlib
import importlib.util
import json
import socket
from collections import Counter
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "evaluation-results/hbq-human-alignment-dryad-full-hbq-analysis-v1/baseline_native_runtime_v5.py"
SHARED = Path.home() / ".codex" / "tools" / "model_work_queue"


def load():
    spec = importlib.util.spec_from_file_location("dryad_baseline_native_runtime_v5", SOURCE)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def package_descriptor(root: Path) -> dict[str, object]:
    files = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.name == "candidate-manifest.json":
            continue
        raw = path.read_bytes()
        files.append({"path": path.relative_to(root).as_posix(), "bytes": len(raw), "sha256": digest(raw)})
    return {
        "schema_version": 7,
        "kind": "complete_candidate_runtime_probe_set",
        "explicit_exclusion": ["candidate-manifest.json"],
        "files": files,
    }


def write_package(root: Path) -> bytes:
    raw = json.dumps(package_descriptor(root), sort_keys=True).encode("utf-8")
    (root / "candidate-manifest.json").write_bytes(raw)
    return raw


def binding(subject, package_raw: bytes) -> dict[str, object]:
    shared = {}
    package = json.loads(package_raw)
    records = {record["path"]: record for record in package["files"]}
    for relative in subject.SHARED_PATHS:
        shared[relative] = records[f"model_work_queue/{relative}"]["sha256"]
    return {
        "schema_version": 2,
        "evidence_class": "baseline_runtime_source_bindings_v5",
        "baseline_plan_sha256": subject.PLAN_SHA256,
        "parent_protocol_sha256": subject.PROTOCOL_SHA256,
        "bridge_path": subject.BRIDGE,
        "bridge_sha256": digest((ROOT / subject.BRIDGE).read_bytes()),
        "shared_runtime_bindings": shared,
        "parent_runtime_manifest_sha256": subject.PARENT_RUNTIME_MANIFEST_SHA256,
        "parent_runtime_loader_sha256": subject.PARENT_RUNTIME_LOADER_SHA256,
        "runtime_package_manifest_sha256": digest(package_raw),
        "helper_source_bindings": {
            subject.V1_BRIDGE: subject.V1_BRIDGE_SHA256,
            subject.V2_BRIDGE: subject.V2_BRIDGE_SHA256,
        },
        "adapter_version": 5,
        "execution_policy": "bounded_nonvisual_deny_wins_attested",
        "tools": "deny_wins_none_attested",
        "identity_evidence": "requested_only",
        "reasoning_attested": False,
        "nonvisual_transport_contract_sha256": subject.NONVISUAL_TRANSPORT_CONTRACT_SHA256,
    }


@pytest.fixture
def synthetic_package(tmp_path: Path) -> dict[str, Path | bytes]:
    subject = load()
    root = tmp_path / "candidate-v5-final"
    root.mkdir()
    for relative in subject.SHARED_PATHS:
        target = root / "model_work_queue" / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((SHARED / relative).read_bytes())
    for number in range(24):
        target = root / "metadata" / f"retained-{number:02d}.txt"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(f"synthetic retained member {number}\n", encoding="utf-8")
    package_raw = write_package(root)
    assert len(json.loads(package_raw)["files"]) == 30
    manifest = tmp_path / "source-bindings-v5.json"
    manifest_raw = json.dumps(binding(subject, package_raw), sort_keys=True).encode("utf-8")
    manifest.write_bytes(manifest_raw)
    return {"root": root, "package_raw": package_raw, "manifest": manifest, "manifest_raw": manifest_raw}


def rewrite_binding(subject, fixture: dict[str, Path | bytes], value: dict[str, object]) -> bytes:
    raw = json.dumps(value, sort_keys=True).encode("utf-8")
    assert isinstance(fixture["manifest"], Path)
    fixture["manifest"].write_bytes(raw)
    fixture["manifest_raw"] = raw
    return raw


def rewrite_package(subject, fixture: dict[str, Path | bytes], mutate) -> tuple[bytes, bytes]:
    assert isinstance(fixture["root"], Path)
    package = json.loads((fixture["root"] / "candidate-manifest.json").read_bytes())
    mutate(package)
    package_raw = json.dumps(package, sort_keys=True).encode("utf-8")
    (fixture["root"] / "candidate-manifest.json").write_bytes(package_raw)
    assert isinstance(fixture["manifest_raw"], bytes)
    value = json.loads(fixture["manifest_raw"])
    value["runtime_package_manifest_sha256"] = digest(package_raw)
    manifest_raw = rewrite_binding(subject, fixture, value)
    fixture["package_raw"] = package_raw
    return package_raw, manifest_raw


def runtime(subject, fixture: dict[str, Path | bytes]):
    assert isinstance(fixture["manifest"], Path)
    assert isinstance(fixture["manifest_raw"], bytes)
    assert isinstance(fixture["root"], Path)
    assert isinstance(fixture["package_raw"], bytes)
    return subject.load_runtime(
        fixture["manifest"],
        expected_manifest_sha256=digest(fixture["manifest_raw"]),
        runtime_package_root=fixture["root"],
        expected_package_manifest_sha256=digest(fixture["package_raw"]),
    )


def test_synthetic_package_loads_private_and_six_shared_modules_without_provider_access(
    synthetic_package: dict[str, Path | bytes], monkeypatch: pytest.MonkeyPatch,
) -> None:
    subject = load()
    original_read = Path.read_bytes
    original_build_class = builtins.__build_class__
    original_socket = socket.socket
    state_root = (Path.home() / ".codex" / "state").resolve()

    def guarded_read(path: Path) -> bytes:
        assert not path.resolve().is_relative_to(state_root), "v5 loader read provider/account state"
        return original_read(path)

    def guarded_class(function, name, *args, **kwargs):
        value = original_build_class(function, name, *args, **kwargs)
        if name == "Broker":
            value.__init__ = lambda *args, **kwargs: pytest.fail("v5 loader constructed Broker")
        return value

    class NoNetworkSocket(original_socket):
        def connect(self, *args, **kwargs):
            pytest.fail("v5 loader attempted network contact")

    monkeypatch.setattr(Path, "read_bytes", guarded_read)
    monkeypatch.setattr(builtins, "__build_class__", guarded_class)
    monkeypatch.setattr(socket, "socket", NoNetworkSocket)
    monkeypatch.setattr(socket, "create_connection", lambda *args, **kwargs: pytest.fail("network contact"))
    value = runtime(subject, synthetic_package)

    assert value.transport.__file__ == str(ROOT / subject.BRIDGE)
    assert value.broker.__file__.startswith(str(synthetic_package["root"]))
    assert len(value.questions) == 178
    assert Counter(question["role"] for question in value.questions) == {
        "domain": 143, "penalty": 18, "supplemental": 17,
    }
    assert value.provenance["provider_calls"] == 0
    assert value.provenance["native_admission"] is False
    assert value.provenance["execution_authority"] is False
    value.verify()


@pytest.mark.parametrize(
    "field,value",
    [
        ("parent_runtime_manifest_sha256", "0" * 64),
        ("parent_runtime_loader_sha256", "0" * 64),
        ("nonvisual_transport_contract_sha256", "0" * 64),
        ("helper_source_bindings", {"wrong.py": "0" * 64}),
        ("reasoning_attested", True),
    ],
)
def test_manifest_rejects_parent_helper_and_contract_drift(
    field: str, value: object, synthetic_package: dict[str, Path | bytes],
) -> None:
    subject = load()
    package_raw = synthetic_package["package_raw"]
    assert isinstance(package_raw, bytes)
    candidate = binding(subject, package_raw)
    candidate[field] = value
    with pytest.raises(ValueError, match="manifest"):
        subject._manifest(json.dumps(candidate).encode("utf-8"))


def test_package_manifest_rejects_duplicate_and_traversal_members(synthetic_package: dict[str, Path | bytes]) -> None:
    subject = load()

    def duplicate(package: dict[str, object]) -> None:
        files = package["files"]
        assert isinstance(files, list)
        files[-1] = dict(files[0])

    rewrite_package(subject, synthetic_package, duplicate)
    with pytest.raises(ValueError, match="member"):
        runtime(subject, synthetic_package)

    synthetic_package = dict(synthetic_package)
    root = synthetic_package["root"]
    assert isinstance(root, Path)
    package_raw = write_package(root)
    synthetic_package["package_raw"] = package_raw

    def traversal(package: dict[str, object]) -> None:
        files = package["files"]
        assert isinstance(files, list)
        files[-1]["path"] = "../outside.py"

    rewrite_package(subject, synthetic_package, traversal)
    with pytest.raises(ValueError, match="member"):
        runtime(subject, synthetic_package)


def test_package_rejects_missing_extra_and_source_drift(synthetic_package: dict[str, Path | bytes]) -> None:
    subject = load()
    root = synthetic_package["root"]
    assert isinstance(root, Path)
    missing = root / "metadata" / "retained-00.txt"
    missing.unlink()
    with pytest.raises(ValueError, match="inventory"):
        runtime(subject, synthetic_package)

    missing.write_text("synthetic retained member 0\n", encoding="utf-8")
    (root / "__pycache__").mkdir()
    (root / "__pycache__" / "extra.pyc").write_bytes(b"not a source member")
    with pytest.raises(ValueError, match="inventory"):
        runtime(subject, synthetic_package)

    (root / "__pycache__" / "extra.pyc").unlink()
    (root / "__pycache__").rmdir()
    (root / "model_work_queue" / "broker.py").write_bytes(b"source drift")
    with pytest.raises(ValueError, match="source pin"):
        runtime(subject, synthetic_package)


def test_verify_rechecks_exact_membership_and_bytes(synthetic_package: dict[str, Path | bytes]) -> None:
    subject = load()
    value = runtime(subject, synthetic_package)
    root = synthetic_package["root"]
    assert isinstance(root, Path)
    (root / "__pycache__").mkdir()
    (root / "__pycache__" / "late.pyc").write_bytes(b"late extra")
    with pytest.raises(ValueError, match="package changed"):
        value.verify()


def test_package_reparse_is_rejected(synthetic_package: dict[str, Path | bytes], monkeypatch: pytest.MonkeyPatch) -> None:
    subject = load()
    root = synthetic_package["root"]
    assert isinstance(root, Path)
    original_lstat = Path.lstat

    def reparse(path: Path):
        info = original_lstat(path)
        if path == root:
            return SimpleNamespace(st_mode=info.st_mode, st_file_attributes=0x400)
        return info

    monkeypatch.setattr(Path, "lstat", reparse)
    with pytest.raises(ValueError, match="link or reparse"):
        runtime(subject, synthetic_package)
