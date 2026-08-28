from __future__ import annotations

import copy
import importlib.util
import json
import os
from pathlib import Path
import platform
import socket
import sys
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "evaluation-results" / "hbq-supplemental-providers-flash-next-linux-portability-v1"
PREFLIGHT_PATH = PACKAGE / "preflight.py"


def load():
    spec = importlib.util.spec_from_file_location("flash_next_linux_portability_test", PREFLIGHT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def fake_unsigned(preflight, root: Path) -> dict[str, object]:
    checks = {key: True for key in ("exclusive_create", "atomic_replace", "directory_fsync_path_exercised", "immutable_target_refusal", "nested_symlink_refusal", "root_symlink_refusal", "sampled_root_identity_stable")}
    return {
        "format_version": 1,
        "study_id": preflight._contract()["study_id"],
        "state": preflight.NO_GO,
        "evidence_classification": preflight.CLASSIFICATION,
        "validation_scope": "schema_and_self_integrity_only_not_native_provenance",
        "interpretation": "exclusive-published self-integrity diagnostic; not native execution or provenance proof",
        "commands": preflight._expected_command(root),
        "host": {"system": "Linux", "release": "fabricated", "version": "fabricated", "machine": "fabricated", "architecture": ["64bit", "fabricated"], "python": {"declared_path": "/fabricated/python", "resolved_path": "/fabricated/python", "sha256": "0" * 64, "bytes": 1, "version": "fabricated", "implementation": "fabricated"}, "filesystem": {"device": 1, "inode": 1, "mode": 0, "block_size": 1, "fragment_size": 1, "blocks": 1, "name_max": 1}},
        "root_identity": {"device": 1, "inode": 1, "file_type": 1},
        "predecessor_assets": preflight.predecessor_bindings(),
        "successor_assets": preflight.successor_bindings(),
        "checks": checks,
        "action_surface": preflight.ACTION_SURFACE,
    }


def write_fake(preflight, root: Path, unsigned: dict[str, object]) -> None:
    root.mkdir()
    evidence = {**unsigned, "self_integrity_sha256": preflight.object_sha256(unsigned)}
    (root / preflight.EVIDENCE_NAME).write_bytes(preflight.canonical(evidence))


def test_plan_is_provider_free_no_go_and_binds_the_exact_predecessor_set(monkeypatch: pytest.MonkeyPatch) -> None:
    preflight = load()

    def no_network(*_args, **_kwargs):
        raise AssertionError("plan must not create a network socket")

    monkeypatch.setattr(socket, "socket", no_network)
    result = preflight.plan()
    assert result["state"] == "NO_GO_PROVIDER_FREE_PORTABILITY_PLAN"
    assert result["evidence_classification"] == "exclusive_published_self_integrity_linux_diagnostic"
    assert {record["path"] for record in result["predecessor_assets"]} == preflight.PREDECESSOR_PATHS
    assert result["action_surface"] == preflight.ACTION_SURFACE
    assert result["native_linux_execution"] == "not_attested"


@pytest.mark.parametrize("mutation", ("duplicate", "missing", "wrong"))
def test_predecessor_binding_requires_exact_unique_path_set(mutation: str) -> None:
    preflight = load()
    assets = copy.deepcopy(preflight._contract()["predecessor"]["assets"])
    if mutation == "duplicate":
        assets[-1]["path"] = assets[0]["path"]
    elif mutation == "missing":
        assets.pop()
    else:
        assets[-1]["path"] = "tests/not-the-bound-test.py"
    with pytest.raises(ValueError, match="Predecessor asset (path set|bindings) drifted"):
        preflight._validate_predecessor_records(assets)


def test_bound_adapter_is_compiled_from_verified_bytes_without_importlib_path_reload() -> None:
    preflight = load()
    assets, contents = preflight._read_predecessor_assets()
    record = next(record for record in assets if record["path"].endswith("/adapter.py"))
    adapter = preflight._load_bound_adapter(contents[record["path"]], record)
    assert adapter.__file__.endswith("adapter.py")
    assert hasattr(adapter, "_atomic_exclusive")
    source = PREFLIGHT_PATH.read_text(encoding="utf-8")
    assert "importlib" not in source


def test_cli_surface_has_no_provider_execution_or_network_implementation() -> None:
    preflight = load()
    assert preflight._contract()["allowed_cli_commands"] == ["plan", "verify", "validate-evidence"]
    source = PREFLIGHT_PATH.read_text(encoding="utf-8")
    for token in ("requests", "urllib.request", "subprocess", "socket", "http.client"):
        assert token not in source


def test_verify_refuses_preexisting_root_before_mutation(tmp_path: Path) -> None:
    preflight = load()
    existing = tmp_path / "already-there"
    existing.mkdir()
    with pytest.raises(ValueError, match="new path"):
        preflight._create_new_external_root(existing)
    assert list(existing.iterdir()) == []


def test_root_identity_drift_is_detected(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    preflight = load()
    expected = preflight._identity(tmp_path)
    monkeypatch.setattr(preflight.os, "fstat", lambda _descriptor: SimpleNamespace(st_dev=expected[0], st_ino=expected[1], st_mode=expected[2]))
    monkeypatch.setattr(preflight, "_identity", lambda _path: (expected[0], expected[1] + 1, expected[2]))
    with pytest.raises(ValueError, match="identity drifted"):
        preflight._assert_root_identity(tmp_path, 0, expected)


def test_self_consistent_fabrication_remains_explicit_non_provenance_diagnostic(tmp_path: Path) -> None:
    preflight = load()
    root = tmp_path / "fabricated"
    write_fake(preflight, root, fake_unsigned(preflight, root))
    result = preflight.validate_evidence(root)
    assert result["state"] == "NO_GO_NATIVE_PORTABILITY_OR_PROMOTION"
    assert result["validation_scope"] == "schema_and_self_integrity_only_not_native_provenance"
    assert "not native execution or provenance proof" in result["interpretation"]


def test_validate_evidence_rejects_tampering_and_invalid_host_ranges(tmp_path: Path) -> None:
    preflight = load()
    root = tmp_path / "tampered"
    unsigned = fake_unsigned(preflight, root)
    unsigned["host"]["python"]["bytes"] = 0
    write_fake(preflight, root, unsigned)
    with pytest.raises(ValueError, match="Python facts drifted"):
        preflight.validate_evidence(root)
    value = json.loads((root / preflight.EVIDENCE_NAME).read_text(encoding="utf-8"))
    value["state"] = "forged"
    (root / preflight.EVIDENCE_NAME).write_bytes(preflight.canonical(value))
    with pytest.raises(ValueError, match="self-integrity drifted"):
        preflight.validate_evidence(root)


def test_verify_is_host_gated_before_mutating_evidence_root(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    preflight = load()
    destination = tmp_path / "must-remain-absent"
    monkeypatch.setattr(preflight.platform, "system", lambda: "Windows")
    with pytest.raises(ValueError, match="requires Linux"):
        preflight.verify(destination)
    assert not os.path.lexists(destination)


@pytest.mark.skipif(platform.system() != "Linux" or sys.platform != "linux", reason="Linux diagnostic must be exercised on Linux")
def test_linux_diagnostic_exercises_bound_adapter_but_remains_no_go(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    preflight = load()
    monkeypatch.setattr(socket, "socket", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("no network implementation may run")))
    result = preflight.verify(tmp_path / "external-diagnostic")
    assert result["state"] == preflight.NO_GO
    assert result["evidence_classification"] == preflight.CLASSIFICATION
    assert all(result["checks"].values())
