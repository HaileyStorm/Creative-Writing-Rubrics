from __future__ import annotations

import json
from pathlib import Path

import pytest

from _scoped_module_loader import load_module


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "evaluation-results" / "hbq-human-alignment-optimizer-v4-development-readout-v1"
readout = load_module(PACKAGE / "analyze.py", name="hanna_v4_development_readout_v1")


def write_json(path: Path, value: object) -> bytes:
    raw = readout.canonical(value); path.write_bytes(raw); return raw


def cell(root: Path, proofs: Path, *, cell_id: str, candidate: str, contact: str) -> Path:
    root.mkdir()
    source = root.parent / "source" / cell_id; source.mkdir(parents=True)
    request = f"request-{cell_id}".encode()
    response = readout.canonical({"structuredOutput": {"scores": {name: 2 for name in readout.DIMENSIONS}, "coverage": {name: True for name in readout.DIMENSIONS}}})
    prepared = {"study_id": "hbq-human-alignment-optimizer-v4-native-subscription-v1", "cell": {"cell_id": cell_id, "item_id": "item-1", "candidate_id": candidate, "prompt_group_id": "group-1"}}
    identity = {"contact_id": contact, "session_id": f"session-{contact}"}
    result = {"study_id": "hbq-human-alignment-optimizer-v4-native-subscription-v1", "state": "native_returned_unprojected", "provider_calls_made": 1, "identity": identity, "native_request_sha256": readout.sha256(request), "native_response_sha256": readout.sha256(response)}
    files = {"native-request.bin": request, "native-response.bin": response, "prepared.json": readout.canonical(prepared), "result.json": readout.canonical(result)}
    for name, raw in files.items(): (root / name).write_bytes(raw)
    inventory = {name: {"bytes": len(raw), "sha256": readout.sha256(raw)} for name, raw in files.items()}
    source_receipt = {"identity": identity}
    source_receipt_raw = write_json(source / "execution-receipt.json", source_receipt)
    source_inventory = {"execution-receipt.json": {"bytes": len(source_receipt_raw), "sha256": readout.sha256(source_receipt_raw)}}
    proof = {"format_version": 1, "study_id": readout.ADMISSION_STUDY, "kind": "completed_grok_admission_proof", "cell_id": cell_id, "destination_root": str(root),
             "destination_inventory": inventory, "destination_result_sha256": readout.sha256(files["result.json"]),
             "deduplication_key": {"cell_id": cell_id, "contact_id": contact, "session_id": identity["session_id"], "native_request_sha256": readout.sha256(request), "native_response_sha256": readout.sha256(response)},
             "admission_contract_sha256": readout.ADMISSION_CONTRACT_SHA256, "admit_py_sha256": readout.ADMIT_PY_SHA256,
             "native_request_sha256": readout.sha256(request), "native_response_sha256": readout.sha256(response),
             "predecessor_contract_sha256": "a" * 64, "predecessor_executor_sha256": "b" * 64, "provider_calls_made": 0,
             "source_cell_root": str(source), "source_exec_executor_sha256": readout.SOURCE_EXECUTOR_SHA256,
             "source_execution_root": str(source.parent), "source_identity_sha256": readout.sha256(readout.canonical(identity)),
             "source_inventory": source_inventory, "source_receipt_sha256": readout.sha256(source_receipt_raw)}
    proof_path = proofs / f"{cell_id}.json"; write_json(proof_path, proof)
    return proof_path


def test_synthetic_proof_cannot_substitute_for_pinned_admission_verifier(tmp_path: Path) -> None:
    observations, proofs = tmp_path / "observations", tmp_path / "proofs"; observations.mkdir(); proofs.mkdir()
    paths = [cell(observations / "cell-a", proofs, cell_id="cell-a", candidate="candidate-a", contact="contact-a")]
    with pytest.raises(ValueError):
        readout.analyze(observation_root=observations, proof_paths=paths, frozen_successor_path=tmp_path / "missing-contract.json", hanna_csv_path=tmp_path / "missing.csv")


def test_rejects_missing_proof_or_unbalanced_coverage(tmp_path: Path) -> None:
    observations, proofs = tmp_path / "observations", tmp_path / "proofs"; observations.mkdir(); proofs.mkdir()
    paths = [cell(observations / "cell-a", proofs, cell_id="cell-a", candidate="candidate-a", contact="contact-a"), cell(observations / "cell-b", proofs, cell_id="cell-b", candidate="candidate-b", contact="contact-b")]
    with pytest.raises(ValueError):
        readout.analyze(observation_root=observations, proof_paths=paths, frozen_successor_path=tmp_path / "missing-contract.json", hanna_csv_path=tmp_path / "missing.csv")
    (observations / "cell-b" / "result.json").unlink()
    with pytest.raises(ValueError):
        readout.analyze(observation_root=observations, proof_paths=paths, frozen_successor_path=tmp_path / "missing-contract.json", hanna_csv_path=tmp_path / "missing.csv")


def test_rejects_unpinned_or_duplicate_contact_proof(tmp_path: Path) -> None:
    observations, proofs = tmp_path / "observations", tmp_path / "proofs"; observations.mkdir(); proofs.mkdir()
    path = cell(observations / "cell-a", proofs, cell_id="cell-a", candidate="candidate-a", contact="contact-a")
    proof = json.loads(path.read_text(encoding="utf-8")); proof["admit_py_sha256"] = "0" * 64; write_json(path, proof)
    with pytest.raises(ValueError, match="identity drifted"):
        readout.analyze(observation_root=observations, proof_paths=[path], frozen_successor_path=tmp_path / "missing-contract.json", hanna_csv_path=tmp_path / "missing.csv")


def test_rejects_self_consistent_substituted_destination_native_evidence() -> None:
    request = b"native request"
    source_response = b'{"source":true}'
    source_identity = {"contact_id": "source-contact", "session_id": "source-session"}
    proof = {
        "native_request_sha256": readout.sha256(request),
        "native_response_sha256": readout.sha256(source_response),
        "source_identity_sha256": readout.sha256(readout.canonical(source_identity)),
    }
    result = {"identity": source_identity, "identity_sha256": readout.sha256(readout.canonical(source_identity))}
    source_verified = {"response": source_response, "identity": source_identity}
    readout._bind_destination_to_source(proof=proof, request=request, response=source_response, result=result,
                                        identity=source_identity, source_verified=source_verified)

    substituted_response = b'{"substituted":true}'
    substituted_identity = {"contact_id": "substituted-contact", "session_id": "substituted-session"}
    substituted_proof = {
        "native_request_sha256": readout.sha256(request),
        "native_response_sha256": readout.sha256(substituted_response),
        "source_identity_sha256": readout.sha256(readout.canonical(source_identity)),
    }
    substituted_result = {"identity": substituted_identity,
                          "identity_sha256": readout.sha256(readout.canonical(substituted_identity))}
    with pytest.raises(ValueError, match="diverged from verified source"):
        readout._bind_destination_to_source(proof=substituted_proof, request=request,
                                            response=substituted_response, result=substituted_result,
                                            identity=substituted_identity, source_verified=source_verified)
