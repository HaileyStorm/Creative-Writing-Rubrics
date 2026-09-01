from __future__ import annotations

import copy
import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = (
    ROOT
    / "evaluation-results"
    / "hbq-supplemental-providers-flash-next-execution-contract-v1"
)
EXECUTOR = PACKAGE / "executor.py"


def load():
    spec = importlib.util.spec_from_file_location(
        "flash_next_execution_contract_test", EXECUTOR
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(spec.name, None)
    return module


def prepare(tmp_path: Path):
    value = load()
    root = tmp_path / "prepared"
    result = value.prepare(root)
    return value, root, result


def complete(value, root: Path) -> None:
    for cell in value.contract()["cells"]:
        value.execute_fixture(root, cell["cell_id"])


def test_two_representative_cells_freeze_exact_assets_payloads_and_no_go_limits() -> (
    None
):
    value = load()
    contract = value.contract()
    assert contract["status"] == "fixture_contract_only_no_go"
    assert contract["execution_policy"] == {
        "fixture_process_limit_per_cell": 1,
        "fixture_subprocess_only": True,
        "native_dispatch_enabled": False,
        "provider_calls_made": 0,
        "remote_fallback_allowed": False,
        "resend_allowed": False,
    }
    assert [(cell["cell_id"], cell["operation"]) for cell in contract["cells"]] == [
        ("flash-next-generation-representative-v1", "generation"),
        ("flash-next-judging-representative-v1", "judging"),
    ]
    assert "NO-GO" in " ".join(contract["evidence_limits"])
    invocation = contract["future_linux_native_invocation"]
    assert invocation["current_implementation"] == "disabled; metadata-only"
    assert invocation["command"][2] == "native-run"
    source = EXECUTOR.read_text(encoding="utf-8")
    for forbidden in ("requests", "urllib", "socket", "http.client"):
        assert forbidden not in source


@pytest.mark.parametrize("mutation", ("duplicate", "missing", "wrong"))
def test_predecessor_set_is_exact_and_not_merely_self_consistent(
    mutation: str,
) -> None:
    value = load()
    records = copy.deepcopy(value.contract()["predecessor_assets"])
    if mutation == "duplicate":
        records[-1]["path"] = records[0]["path"]
    elif mutation == "missing":
        records.pop()
    else:
        records[-1]["path"] = "README.md"
    with pytest.raises(
        ValueError, match="Predecessor (asset binding|path set|bindings|path) drifted"
    ):
        value._validate_predecessors(records)


def test_self_consistent_no_go_metadata_mutation_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    value = load()
    forged = copy.deepcopy(value.contract())
    forged["future_linux_native_invocation"]["current_implementation"] = "enabled"
    unsigned = dict(forged)
    unsigned.pop("semantic_contract_sha256")
    forged["semantic_contract_sha256"] = value.object_sha256(unsigned)
    monkeypatch.setattr(value, "_read_json", lambda *_args, **_kwargs: forged)
    with pytest.raises(ValueError, match="future Linux invocation"):
        value.contract()


def test_prepare_fixture_subprocess_receipts_and_replay_are_exact_and_single_launch(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    value, root, prepared = prepare(tmp_path)
    assert prepared == {
        "cells": 2,
        "fixture_process_launches": 0,
        "native_endpoint_contact_cardinality": "unproven_fixture_only",
        "provider_calls_made": 0,
        "state": "prepared_fixture_only",
    }
    calls = {"count": 0}
    original = value.subprocess.run

    def counted(*args, **kwargs):
        calls["count"] += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(value.subprocess, "run", counted)
    first = [
        value.execute_fixture(root, cell["cell_id"])
        for cell in value.contract()["cells"]
    ]
    assert calls["count"] == 2
    assert all(
        row["fixture_process_launches"] == 1 and row["provider_calls_made"] == 0
        for row in first
    )
    repeat = value.execute_fixture(root, value.contract()["cells"][0]["cell_id"])
    assert repeat["state"] == "terminal_recorded_no_resend" and calls["count"] == 2
    assert all(
        receipt["fixture_runtime"]["executor"]["sha256"]
        == value.sha256(EXECUTOR.read_bytes())
        for receipt in first
    )
    assert all(
        (root / cell["cell_id"] / "raw-stderr.txt").read_bytes() == b""
        for cell in value.contract()["cells"]
    )
    replay = value.replay(root)
    assert replay == {
        "cells": 2,
        "completed_cells": 2,
        "fixture_process_launches": 2,
        "native_endpoint_contact_cardinality": "unproven_fixture_only",
        "provider_calls_made": 0,
        "state": "fixture_only_non_native_no_go",
    }


def test_payload_tampering_is_rejected_before_any_fixture_process(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    value, root, _ = prepare(tmp_path)
    cell_id = value.contract()["cells"][0]["cell_id"]
    payload = root / cell_id / "outbound-payload.json"
    payload.write_bytes(b"tampered\n")
    monkeypatch.setattr(
        value.subprocess,
        "run",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("fixture must not launch")
        ),
    )
    with pytest.raises(ValueError, match="outbound payload"):
        value.execute_fixture(root, cell_id)


def test_raw_response_receipt_and_identity_tampering_are_rejected(
    tmp_path: Path,
) -> None:
    value, root, _ = prepare(tmp_path)
    complete(value, root)
    cells = value.contract()["cells"]
    first, second = (root / cell["cell_id"] for cell in cells)
    raw = second / "raw-response.json"
    original_raw = raw.read_bytes()
    forged = json.loads(original_raw)
    forged["output"] = {"evidence": "forged", "score": 3.0}
    raw.write_bytes(value.canonical(forged))
    with pytest.raises(ValueError, match="stream binding"):
        value.replay(root)
    raw.write_bytes(original_raw)

    first_identity = json.loads((first / "receipt.json").read_bytes())["identity"]
    forged = json.loads(original_raw)
    forged["identity"] = first_identity
    forged_raw = value.canonical(forged)
    raw.write_bytes(forged_raw)
    receipt = json.loads((second / "receipt.json").read_bytes())
    receipt["identity"] = first_identity
    receipt["raw_response_sha256"] = value.sha256(forged_raw)
    (second / "receipt.json").write_bytes(value.canonical(receipt))
    process_result = json.loads((second / "fixture-process-result.json").read_bytes())
    process_result["stdout"] = {
        "bytes": len(forged_raw),
        "sha256": value.sha256(forged_raw),
    }
    (second / "fixture-process-result.json").write_bytes(
        value.canonical(process_result)
    )
    with pytest.raises(
        ValueError, match="identity is duplicate, misassociated, or malformed"
    ):
        value.replay(root)


def test_duplicate_or_noncanonical_generated_json_and_receipt_only_state_are_rejected(
    tmp_path: Path,
) -> None:
    value, root, _ = prepare(tmp_path)
    cell_id = value.contract()["cells"][0]["cell_id"]
    intent = root / cell_id / "intent.json"
    original = intent.read_bytes()
    intent.write_bytes(b'{"cell_id":"x","cell_id":"x"}\n')
    with pytest.raises(ValueError, match="duplicate key"):
        value.validate_prepared(root)
    intent.write_bytes(original.replace(b"{", b"{\n", 1))
    with pytest.raises(ValueError, match="canonical JSON"):
        value.validate_prepared(root)
    intent.write_bytes(original)
    (root / cell_id / "receipt.json").write_bytes(value.canonical({}))
    assert (
        value.execute_fixture(root, cell_id)["state"]
        == "reconcile_required_after_fixture_process_launch"
    )


def test_postlaunch_fixture_failure_is_terminal_reconcile_without_resend(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    value, root, _ = prepare(tmp_path)
    calls = {"count": 0}

    def failed(*_args, **_kwargs):
        calls["count"] += 1
        return SimpleNamespace(returncode=1, stderr=b"fixture failure", stdout=b"")

    monkeypatch.setattr(value.subprocess, "run", failed)
    cell_id = value.contract()["cells"][0]["cell_id"]
    first = value.execute_fixture(root, cell_id)
    second = value.execute_fixture(root, cell_id)
    assert (
        first["state"]
        == second["state"]
        == "reconcile_required_after_fixture_process_launch"
    )
    assert calls["count"] == 1
    with pytest.raises(ValueError, match="ambiguous"):
        value.replay(root)


def test_fixture_launch_exception_still_prevents_a_resend(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    value, root, _ = prepare(tmp_path)
    calls = {"count": 0}

    def unavailable(*_args, **_kwargs):
        calls["count"] += 1
        raise OSError("fixture unavailable")

    monkeypatch.setattr(value.subprocess, "run", unavailable)
    cell_id = value.contract()["cells"][0]["cell_id"]
    with pytest.raises(OSError, match="fixture unavailable"):
        value.execute_fixture(root, cell_id)
    assert (
        value.execute_fixture(root, cell_id)["state"]
        == "reconcile_required_after_fixture_process_launch"
    )
    assert calls["count"] == 1


def test_native_run_is_explicitly_disabled_and_fixture_response_is_local_only(
    tmp_path: Path,
) -> None:
    completed = subprocess.run(
        [sys.executable, str(EXECUTOR), "native-run"],
        capture_output=True,
        check=False,
        text=True,
    )
    assert completed.returncode == 2
    assert "deliberately disabled" in completed.stderr
    value, root, _ = prepare(tmp_path)
    intent = root / value.contract()["cells"][0]["cell_id"] / "intent.json"
    result = subprocess.run(
        [sys.executable, str(EXECUTOR), "fixture-response", "--intent", str(intent)],
        capture_output=True,
        check=True,
    )
    envelope = json.loads(result.stdout)
    assert envelope["fixture_only"] is True
    assert envelope["identity"]["provider"] == "fixture-only"
    assert envelope["identity"]["runtime"] == "local-fixture-subprocess"
