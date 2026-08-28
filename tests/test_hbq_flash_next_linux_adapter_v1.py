from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
ADAPTER_PATH = ROOT / "evaluation-results" / "hbq-supplemental-providers-flash-next-v1" / "adapter.py"
SPEC = importlib.util.spec_from_file_location("flash_next_adapter", ADAPTER_PATH)
assert SPEC and SPEC.loader
adapter = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = adapter
SPEC.loader.exec_module(adapter)


def write(path: Path, value: bytes) -> Path:
    path.write_bytes(value)
    return path


def inputs(tmp_path: Path) -> tuple[Path, dict[str, object], list[Path]]:
    study = adapter._load_study()
    row = next(row for row in study._read_method_inputs() if row["request"]["method_id"] == "hbq" and row["request"]["repetition"] == 1 and row["request"]["batch_ordinal"] == 1)
    root = tmp_path / "canonical-root"
    root.mkdir(parents=True)
    root_binding = {"format_version": 1, "study_id": study.contract()["study_id"], "contract_sha256": study.contract()["semantic_contract_sha256"], "canonical_root_id": study.contract()["canonical_root"]["identity"], "root_path_sha256": hashlib.sha256(str(root).replace("\\", "/").encode("utf-8")).hexdigest()}
    root_file = write(tmp_path / "canonical-root.json", adapter.canonical(root_binding))
    prompt, schema, sampler = b"prompt-v1", b'{"type":"object"}\n', b'{"temperature":0}\n'
    logical_cell = {"condition_id": "flash_next_custom", "request": row["request"]}
    request = {"format_version": 1, "study_id": study.contract()["study_id"], "condition_id": logical_cell["condition_id"], "request": row["request"], "source_artifact": row["source_artifact"], "question_ids": row["question_ids"], "prompt_sha256": hashlib.sha256(prompt).hexdigest(), "schema_sha256": hashlib.sha256(schema).hexdigest(), "sampler_sha256": hashlib.sha256(sampler).hexdigest()}
    request_file = write(tmp_path / "request.json", adapter.canonical(request))
    route = {"format_version": 1, "endpoint": "https://runner.example/v1", "model": "flash-next", "transport": "linux-native-cli-v1", "provider_identity": "operator-managed-route"}
    disclosure = {"format_version": 1, "destination": {key: route[key] for key in ("endpoint", "model", "transport", "provider_identity")}, "route_sha256": adapter.digest(route), "outbound_request": {"bytes": len(request_file.read_bytes()), "sha256": hashlib.sha256(request_file.read_bytes()).hexdigest()}, "local_first": True}
    acknowledgement = {"format_version": 1, "acknowledged_by": "owner", "acknowledgement": "owner assertion only", "disclosure_sha256": adapter.digest(disclosure)}
    zero_charge = {"format_version": 1, "status": "asserted_zero_charge_route", "route_sha256": adapter.digest(route), "issued_by": "owner", "receipt": "asserted-zero-new-spend"}
    files = [request_file, write(tmp_path / "prompt.txt", prompt), write(tmp_path / "schema.json", schema), write(tmp_path / "sampler.json", sampler), write(tmp_path / "route.json", adapter.canonical(route)), write(tmp_path / "disclosure.json", adapter.canonical(disclosure)), write(tmp_path / "ack.json", adapter.canonical(acknowledgement)), write(tmp_path / "zero.json", adapter.canonical(zero_charge))]
    return root_file, logical_cell, [root, *files]


def prepare(tmp_path: Path) -> tuple[Path, dict[str, object], dict[str, object], list[Path]]:
    root_file, cell, files = inputs(tmp_path)
    result = adapter.prepare(files[0], root_file, cell, *files[1:])
    return root_file, cell, result, files


def test_offline_prepare_persists_owner_assertions_and_exact_input_bytes(tmp_path: Path) -> None:
    _, _, result, files = prepare(tmp_path)
    intent = result["intent"]
    assert result["state"] == "prepared"
    assert intent["pairable"] is False and intent["dispatch"]["enabled"] is False
    assert set(intent["owner_assertions"]) == {"route", "disclosure", "acknowledgement", "zero_charge", "canonical_root"}
    assert set(intent["input_assets"]) == {"prompt", "schema", "sampler"}
    for key, receipt in intent["input_assets"].items():
        assert (files[0] / receipt["relative_path"]).read_bytes() == files[{"prompt": 2, "schema": 3, "sampler": 4}[key]].read_bytes()


def test_journal_rejects_remint_and_resume_revalidates(tmp_path: Path) -> None:
    root_file, cell, result, files = prepare(tmp_path)
    resumed = adapter.prepare(files[0], root_file, cell, *files[1:])
    assert resumed["state"] == "resumed"
    request = json.loads(files[1].read_text(encoding="utf-8"))
    request["prompt_sha256"] = "0" * 64
    files[1].write_bytes(adapter.canonical(request))
    with pytest.raises(ValueError):
        adapter.prepare(files[0], root_file, cell, *files[1:])


def test_distinct_explicit_roots_are_distinct_non_authoritative_workspaces(tmp_path: Path) -> None:
    _, _, first, _ = prepare(tmp_path / "one")
    _, _, second, _ = prepare(tmp_path / "two")
    assert first["state"] == second["state"] == "prepared"


def test_raw_response_is_never_native_or_pairable(tmp_path: Path) -> None:
    root_file, cell, _, files = prepare(tmp_path)
    response = write(tmp_path / "response.bin", b"raw bytes")
    result = adapter.record_response(files[0], root_file, cell, response)
    assert result["state"] == "recorded_untrusted_nonpairable"
    assert result["receipt"]["provenance"]["classification"] == "untrusted_raw"
    assert result["receipt"]["pairable"] is False


@pytest.mark.parametrize("endpoint", ["http://runner.example/v1", "https://user@runner.example/v1", "https://runner.example/v1#x", "https://runner.example/v1?token=x", "https://runner.example /v1", "https://RUNNER.example/v1", "https://runner.example:0/v1", "https://runner.example:65536/v1", "https://runner.example/%00"])
def test_route_url_is_strictly_canonical(endpoint: str) -> None:
    with pytest.raises(ValueError):
        adapter.parse_route({"format_version": 1, "endpoint": endpoint, "model": "flash-next", "transport": "linux", "provider_identity": "route"})


def test_cli_cannot_prepare_or_dispatch() -> None:
    for command in ("prepare", "dispatch", "record-response"):
        completed = subprocess.run([sys.executable, str(ADAPTER_PATH), command], capture_output=True, text=True)
        assert completed.returncode == 2
        assert "offline-only" in completed.stderr
