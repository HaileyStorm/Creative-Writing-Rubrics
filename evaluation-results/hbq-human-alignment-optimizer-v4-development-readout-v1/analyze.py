#!/usr/bin/env python3
"""Provider-free, descriptive-only HANNA development readout from admitted Grok cells."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import statistics
from pathlib import Path
from typing import Any, Mapping, Sequence


STUDY_ID = "hbq-human-alignment-optimizer-v4-development-readout-v1"
DIMENSIONS = ("Relevance", "Coherence", "Empathy", "Surprise", "Engagement", "Complexity")
ADMISSION_STUDY = "hbq-human-alignment-optimizer-v4-native-admission-v1"
ADMISSION_CONTRACT_SHA256 = "43f8bdab947a360224d5f9c02d0e69f5dd98fc261bc8d5e94dc17fc9997f92e8"
ADMIT_PY_SHA256 = "a1c18d224c40e51a822cf2a46b2da273fef37d47df0fe207d1abe8b49bc75304"
SOURCE_EXECUTOR_SHA256 = "5d2bd6871fe2013b8af5e166d89eeb020ff98889ce30494dd8889f7bee2d942f"
HERE = Path(__file__).resolve().parent
ADMIT_PATH = HERE.parent / "hbq-human-alignment-optimizer-v4-native-admission-v1" / "admit.py"


def canonical(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _read_json(path: Path, *, label: str) -> dict[str, Any]:
    raw = path.read_bytes()
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"HANNA readout {label} is invalid JSON") from error
    if not isinstance(value, dict) or canonical(value) != raw:
        raise ValueError(f"HANNA readout {label} is noncanonical")
    return value


def _inventory(root: Path, inventory: Any, *, label: str) -> None:
    if not isinstance(inventory, Mapping):
        raise ValueError(f"HANNA readout admission proof lacks {label} inventory")
    for name, binding in inventory.items():
        if not isinstance(name, str) or not isinstance(binding, Mapping):
            raise ValueError("HANNA readout admission inventory is malformed")
        path = root / name
        if binding == {"directory": True}:
            if not path.is_dir() or path.is_symlink():
                raise ValueError("HANNA readout admitted directory is missing or reparsed")
            continue
        if set(binding) != {"bytes", "sha256"} or not path.is_file() or path.is_symlink():
            raise ValueError("HANNA readout admitted artifact is missing or reparsed")
        raw = path.read_bytes()
        if binding["bytes"] != len(raw) or binding["sha256"] != sha256(raw):
            raise ValueError("HANNA readout admitted artifact binding drifted")


def _proofs(proof_paths: Sequence[Path]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for path in proof_paths:
        proof = _read_json(Path(path), label="admission proof")
        required = {"admission_contract_sha256", "admit_py_sha256", "cell_id", "deduplication_key", "destination_inventory", "destination_result_sha256", "destination_root", "format_version", "kind", "native_request_sha256", "native_response_sha256", "predecessor_contract_sha256", "predecessor_executor_sha256", "provider_calls_made", "source_cell_root", "source_exec_executor_sha256", "source_execution_root", "source_identity_sha256", "source_inventory", "source_receipt_sha256", "study_id"}
        if set(proof) != required or proof.get("format_version") != 1 or proof.get("study_id") != ADMISSION_STUDY or proof.get("kind") != "completed_grok_admission_proof" or proof.get("admission_contract_sha256") != ADMISSION_CONTRACT_SHA256 or proof.get("admit_py_sha256") != ADMIT_PY_SHA256 or proof.get("source_exec_executor_sha256") != SOURCE_EXECUTOR_SHA256 or proof.get("provider_calls_made") != 0:
            raise ValueError("HANNA readout admission proof identity drifted")
        cell_id = proof.get("cell_id")
        if not isinstance(cell_id, str) or cell_id in result:
            raise ValueError("HANNA readout proof cell IDs are missing or duplicate")
        result[cell_id] = proof
    return result


def _admission_context(*, frozen_successor_path: Path, hanna_csv_path: Path) -> tuple[Any, Any, Any, Mapping[str, Any]]:
    raw = ADMIT_PATH.read_bytes()
    if sha256(raw) != ADMIT_PY_SHA256:
        raise ValueError("HANNA readout admission verifier bytes drifted")
    spec = importlib.util.spec_from_file_location("_hanna_readout_pinned_admission", ADMIT_PATH)
    if spec is None or spec.loader is None:
        raise ValueError("HANNA readout cannot load admission verifier")
    admission = importlib.util.module_from_spec(spec); spec.loader.exec_module(admission)
    admission.contract()
    predecessor, execution = admission._load_pinned()
    schedule = predecessor.derive_schedule(frozen_successor_path=Path(frozen_successor_path), hanna_csv_path=Path(hanna_csv_path))
    return admission, predecessor, execution, schedule


def _bind_destination_to_source(*, proof: Mapping[str, Any], request: bytes, response: bytes,
                                result: Mapping[str, Any], identity: Mapping[str, Any],
                                source_verified: Mapping[str, Any]) -> None:
    """Require the admitted copy to retain the verified historical native evidence exactly."""
    source_response = source_verified["response"]
    source_identity = source_verified["identity"]
    result_identity = result.get("identity")
    if (response != source_response or identity != source_identity or result_identity != source_identity
            or result.get("identity_sha256") != sha256(canonical(source_identity))
            or proof.get("native_request_sha256") != sha256(request)
            or proof.get("native_response_sha256") != sha256(response)
            or proof.get("native_response_sha256") != sha256(source_response)
            or proof.get("source_identity_sha256") != sha256(canonical(source_identity))):
        raise ValueError("HANNA readout destination native evidence diverged from verified source")


def _observation(root: Path, proof: Mapping[str, Any], *, admission: Any, predecessor: Any, execution: Any,
                 schedule: Mapping[str, Any], frozen_successor_path: Path, hanna_csv_path: Path) -> dict[str, Any]:
    _inventory(root, proof["destination_inventory"], label="destination")
    source = Path(proof["source_cell_root"])
    if source.name != proof["cell_id"] or not source.is_dir() or source.is_symlink():
        raise ValueError("HANNA readout admission proof source root is unsafe")
    _inventory(source, proof["source_inventory"], label="source")
    derive_schedule = predecessor.derive_schedule
    predecessor.derive_schedule = lambda **_kwargs: schedule
    try:
        row, payload, task, settings, source_verified = admission._historical_grok_receipt(
            execution=execution, predecessor=predecessor, source_root=Path(proof["source_execution_root"]),
            cell_id=proof["cell_id"], frozen_successor_path=Path(frozen_successor_path), hanna_csv_path=Path(hanna_csv_path),
        )
    finally:
        predecessor.derive_schedule = derive_schedule
    prepared, result = _read_json(root / "prepared.json", label="prepared record"), _read_json(root / "result.json", label="result")
    request, response = (root / "native-request.bin").read_bytes(), (root / "native-response.bin").read_bytes()
    cell = prepared.get("cell")
    identity = result.get("identity")
    if (not isinstance(cell, Mapping) or not isinstance(identity, Mapping) or prepared.get("study_id") != "hbq-human-alignment-optimizer-v4-native-subscription-v1"
            or result.get("study_id") != "hbq-human-alignment-optimizer-v4-native-subscription-v1" or result.get("state") != "native_returned_unprojected"
            or result.get("provider_calls_made") != 1 or result.get("native_request_sha256") != sha256(request)
            or result.get("native_response_sha256") != sha256(response)):
        raise ValueError("HANNA readout native preparation/result/request/response binding drifted")
    key = proof.get("deduplication_key")
    source_receipt = source_verified["receipt"]
    source_identity = source_verified["identity"]
    disclosure, acknowledgement, route_proof, expected_prepared = admission._destination_base(predecessor, row, schedule, payload)
    expected_intent = predecessor._expected_intent(row, expected_prepared)
    if (_read_json(root / "prepared.json", label="prepared record") != expected_prepared
            or (root / "outbound-payload.json").read_bytes() != payload or request != task
            or _read_json(root / "intent.json", label="intent") != expected_intent
            or _read_json(root / "effective-settings.json", label="effective settings") != settings
            or proof.get("source_inventory") != source_verified["source_inventory"]
            or proof.get("source_receipt_sha256") != sha256(canonical(source_receipt)) or proof.get("source_identity_sha256") != sha256(canonical(source_identity))
            or not isinstance(key, Mapping) or key.get("cell_id") != cell.get("cell_id") or key.get("native_request_sha256") != sha256(request)
            or key.get("native_response_sha256") != sha256(response) or key.get("contact_id") != identity.get("contact_id")
            or key.get("session_id") != identity.get("session_id") or proof.get("destination_result_sha256") != sha256(canonical(result))):
        raise ValueError("HANNA readout admission proof is misassociated")
    _bind_destination_to_source(proof=proof, request=request, response=response, result=result,
                                identity=identity, source_verified=source_verified)
    try:
        envelope = json.loads(response.decode("utf-8"))
        structured = envelope["structuredOutput"]
        scores, coverage = structured["scores"], structured["coverage"]
    except (UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError) as error:
        raise ValueError("HANNA readout native structured response is invalid") from error
    if (set(scores) != set(DIMENSIONS) or set(coverage) != set(DIMENSIONS)
            or any(type(scores[name]) not in {int, float} or not 0 <= float(scores[name]) <= 5 for name in DIMENSIONS)
            or any(type(coverage[name]) is not bool for name in DIMENSIONS)):
        raise ValueError("HANNA readout native response score/coverage shape drifted")
    return {"cell_id": cell["cell_id"], "item_id": cell["item_id"], "candidate_id": cell["candidate_id"],
            "prompt_group_id": cell["prompt_group_id"], "request_sha256": sha256(request), "response_sha256": sha256(response),
            "contact_id": identity["contact_id"], "session_id": identity["session_id"], "scores": {name: float(scores[name]) for name in DIMENSIONS},
            "coverage_complete": all(coverage[name] for name in DIMENSIONS)}


def analyze(*, observation_root: Path, proof_paths: Sequence[Path], frozen_successor_path: Path, hanna_csv_path: Path) -> dict[str, Any]:
    proofs = _proofs(proof_paths)
    anchor = Path(observation_root)
    if not anchor.is_dir() or anchor.is_symlink():
        raise ValueError("HANNA readout observation anchor is missing or reparsed")
    roots: dict[str, Path] = {}
    for cell_id, proof in proofs.items():
        destination = proof.get("destination_root")
        root = Path(destination) if isinstance(destination, str) else None
        if root is None or root.name != cell_id or not root.is_dir() or root.is_symlink():
            raise ValueError("HANNA readout admission proof refers to a missing or unsafe observation root")
        try:
            root.resolve().relative_to(anchor.resolve())
            Path(proof["source_cell_root"]).resolve().relative_to(anchor.resolve())
        except ValueError as error:
            raise ValueError("HANNA readout observation destinations escape the approved anchor") from error
        roots[cell_id] = root
    admission, predecessor, execution, schedule = _admission_context(frozen_successor_path=Path(frozen_successor_path), hanna_csv_path=Path(hanna_csv_path))
    rows = [_observation(roots[cell_id], proof, admission=admission, predecessor=predecessor, execution=execution, schedule=schedule, frozen_successor_path=Path(frozen_successor_path), hanna_csv_path=Path(hanna_csv_path)) for cell_id, proof in sorted(proofs.items())]
    contacts = {(row["contact_id"], row["session_id"], row["request_sha256"], row["response_sha256"]) for row in rows}
    if len(contacts) != len(rows) or len({row["contact_id"] for row in rows}) != len(rows) or len({row["session_id"] for row in rows}) != len(rows):
        raise ValueError("HANNA readout duplicate contact/session/request/response evidence")
    if len({(row["item_id"], row["candidate_id"]) for row in rows}) != len(rows):
        raise ValueError("HANNA readout duplicate item/candidate observation")
    candidates = sorted({row["candidate_id"] for row in rows})
    incomplete_count = sum(not row["coverage_complete"] for row in rows)
    complete_rows = [row for row in rows if row["coverage_complete"]]
    items = sorted({row["item_id"] for row in complete_rows if {candidate for candidate in candidates if (row["item_id"], candidate) in {(item["item_id"], item["candidate_id"]) for item in complete_rows}} == set(candidates)})
    expected = {(item, candidate) for item in items for candidate in candidates}
    actual = {(row["item_id"], row["candidate_id"]) for row in complete_rows if row["item_id"] in items}
    if not items or len(actual) != len(expected) or actual != expected:
        raise ValueError("HANNA readout requires balanced complete candidate coverage per included item")
    unbalanced_count = len(complete_rows) - len(actual)
    rows = [row for row in complete_rows if row["item_id"] in items]
    metrics = []
    for candidate in candidates:
        candidate_rows = [row for row in rows if row["candidate_id"] == candidate]
        metrics.append({"candidate_id": candidate, "included_item_count": len(candidate_rows),
                        "dimension_means": {name: statistics.fmean(row["scores"][name] for row in candidate_rows) for name in DIMENSIONS},
                        "mean_six_dimension_score": statistics.fmean(row["scores"][name] for row in candidate_rows for name in DIMENSIONS)})
    return {"format_version": 1, "study_id": STUDY_ID, "kind": "balanced_partial_native_grok_development_readout",
            "status": "descriptive_partial_development_only", "included": {"cell_count": len(rows), "item_ids": items, "candidate_ids": candidates, "excluded_incomplete_coverage_cells": incomplete_count, "excluded_complete_but_unbalanced_item_cells": unbalanced_count},
            "observations": [{key: row[key] for key in ("cell_id", "item_id", "candidate_id", "prompt_group_id", "request_sha256", "response_sha256", "contact_id", "session_id")} for row in rows],
            "metrics": metrics,
            "claim_limits": ["No candidate selection claim", "No HANNA alignment claim", "No Grok/Sol generalization or agreement claim", "No confirmation, runtime, or revision-gain claim"]}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--observation-root", type=Path, required=True)
    parser.add_argument("--admission-proof", type=Path, action="append", required=True)
    parser.add_argument("--frozen-successor-path", type=Path, required=True)
    parser.add_argument("--hanna-csv-path", type=Path, required=True)
    args = parser.parse_args()
    print(canonical(analyze(observation_root=args.observation_root, proof_paths=args.admission_proof, frozen_successor_path=args.frozen_successor_path, hanna_csv_path=args.hanna_csv_path)).decode("utf-8"), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
