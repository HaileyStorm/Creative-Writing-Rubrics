"""Provider-free admission of one immutable exec-v3 Sol local lifecycle."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import stat
import uuid
from pathlib import Path
from types import ModuleType
from typing import Any, Iterable, Mapping


HERE = Path(__file__).resolve().parent
STUDY_ID = "hbq-human-alignment-optimizer-v4-sol-local-lifecycle-admission-v1"
CONTRACT_PATH = HERE / "study-contract.json"
EXEC_PATH = HERE.parent / "hbq-human-alignment-optimizer-v4-native-subscription-exec-v3" / "executor.py"
EXEC_CONTRACT_PATH = EXEC_PATH.with_name("study-contract.json")
EXEC_SHA256 = "cea177b5185a84b682bd5271ae7384cd7742add872d31b45227433d72c7f7e90"
EXEC_CONTRACT_SHA256 = "d92970c60a538a229c8f5470d53e8fd3dd4d163aff25b0110b6453f6caf080f5"
RESULT_NAME = "result.json"
DEDUPLICATION_FIELDS = frozenset({"cell_id", "contact_id", "session_id", "request_sha256", "final_response_sha256"})
RESULT_FIELDS = frozenset({"format_version", "study_id", "kind", "cell_id", "state", "provider_calls_made", "provider_attested", "native_endpoint_contact_cardinality", "native_contact_proven", "evidence_status", "source_receipt_sha256", "deduplication_key"})
PROOF_FIELDS = frozenset({"format_version", "study_id", "kind", "provider_calls_made", "cell_id", "source_execution_root", "source_cell_root", "destination_root", "exec_v3_executor_sha256", "exec_v3_contract_sha256", "admit_py_sha256", "admission_contract_sha256", "source_inventory", "destination_inventory", "source_receipt_sha256", "destination_result_sha256", "deduplication_key", "evidence_status", "provider_attested"})


def _sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _canonical(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _absolute(path: Path) -> Path:
    return Path(os.path.abspath(os.fspath(path)))


def _reject_reparse(path: Path, info: os.stat_result) -> None:
    if stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)):
        raise ValueError(f"HANNA Sol lifecycle admission forbids reparse points: {path}")


def _plain_ancestry(path: Path, *, include_leaf: bool) -> None:
    absolute = _absolute(path)
    current = Path(absolute.anchor)
    parts = absolute.parts[1:]
    for part in parts[:len(parts) if include_leaf else len(parts) - 1]:
        current /= part
        try:
            _reject_reparse(current, os.lstat(current))
        except OSError as error:
            raise ValueError(f"HANNA Sol lifecycle admission path unavailable: {current}") from error


def _stable_bytes(path: Path) -> bytes:
    path = _absolute(path)
    _plain_ancestry(path, include_leaf=True)
    before = os.lstat(path)
    if not stat.S_ISREG(before.st_mode):
        raise ValueError(f"HANNA Sol lifecycle admission requires regular file: {path}")
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        opened = os.fstat(descriptor)
        before_identity = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
        if before_identity != (opened.st_dev, opened.st_ino, opened.st_size, opened.st_mtime_ns):
            raise ValueError(f"HANNA Sol lifecycle admission file identity drifted: {path}")
        chunks: list[bytes] = []
        while chunk := os.read(descriptor, 1024 * 1024):
            chunks.append(chunk)
        after_open, after_path = os.fstat(descriptor), os.lstat(path)
        if (opened.st_dev, opened.st_ino, opened.st_size, opened.st_mtime_ns, opened.st_ctime_ns) != (after_open.st_dev, after_open.st_ino, after_open.st_size, after_open.st_mtime_ns, after_open.st_ctime_ns) or before_identity != (after_path.st_dev, after_path.st_ino, after_path.st_size, after_path.st_mtime_ns):
            raise ValueError(f"HANNA Sol lifecycle admission file changed during read: {path}")
        return b"".join(chunks)
    finally:
        os.close(descriptor)


def _new_file(path: Path, value: bytes) -> None:
    _plain_ancestry(path.parent, include_leaf=True)
    try:
        with path.open("xb") as handle:
            handle.write(value)
            handle.flush()
            os.fsync(handle.fileno())
    except FileExistsError as error:
        raise ValueError(f"HANNA Sol lifecycle admission refuses overwrite: {path}") from error


def _load_exact(path: Path, expected_sha256: str, name: str) -> ModuleType:
    raw = _stable_bytes(path)
    if _sha(raw) != expected_sha256:
        raise ValueError("HANNA Sol lifecycle admission pinned dependency bytes drifted")
    module = ModuleType(name)
    module.__file__ = str(path)
    exec(compile(raw, str(path), "exec"), module.__dict__)
    if _sha(_stable_bytes(path)) != expected_sha256:
        raise ValueError("HANNA Sol lifecycle admission pinned dependency changed during load")
    return module


def _load_execution() -> ModuleType:
    if _sha(_stable_bytes(EXEC_CONTRACT_PATH)) != EXEC_CONTRACT_SHA256:
        raise ValueError("HANNA Sol lifecycle admission pinned exec-v3 contract drifted")
    execution = _load_exact(EXEC_PATH, EXEC_SHA256, "_hanna_sol_lifecycle_exec_v3")
    if execution.STUDY_ID != "hbq-human-alignment-optimizer-v4-native-subscription-exec-v3":
        raise ValueError("HANNA Sol lifecycle admission predecessor identity drifted")
    return execution


def contract() -> dict[str, Any]:
    raw = _stable_bytes(CONTRACT_PATH)
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("HANNA Sol lifecycle admission contract is invalid") from error
    expected = {
        "format_version": 1, "study_id": STUDY_ID,
        "kind": "provider_free_sol_local_lifecycle_admission_descendant",
        "predecessor": {"study_id": "hbq-human-alignment-optimizer-v4-native-subscription-exec-v3", "executor_sha256": EXEC_SHA256, "contract_sha256": EXEC_CONTRACT_SHA256},
        "admission": {"provider_calls_made": 0, "source_immutability": "required", "historical_route_replay": "pinned_exec_v3_verifier_with_persisted_route_evidence_only", "evidence_status": "local_lifecycle_verified_native_endpoint_contact_cardinality_unproven", "provider_attested": False, "destination_shape": "exact_exec_v3_artifact_clone_plus_admission_result", "deduplication": "proof_binds_cell_and_local_identity_and_downstream_must_deduplicate"},
    }
    if value != expected:
        raise ValueError("HANNA Sol lifecycle admission contract identity drifted")
    return value


def _inventory(root: Path) -> dict[str, dict[str, Any]]:
    _plain_ancestry(root, include_leaf=True)
    result: dict[str, dict[str, Any]] = {}
    try:
        paths = sorted(root.rglob("*"), key=lambda path: path.as_posix())
    except OSError as error:
        raise ValueError("HANNA Sol lifecycle admission source inventory unavailable") from error
    for path in paths:
        info = os.lstat(path)
        _reject_reparse(path, info)
        rel = path.relative_to(root).as_posix()
        if stat.S_ISDIR(info.st_mode):
            result[rel] = {"directory": True}
        elif stat.S_ISREG(info.st_mode):
            raw = _stable_bytes(path)
            result[rel] = {"bytes": len(raw), "sha256": _sha(raw)}
        else:
            raise ValueError("HANNA Sol lifecycle admission source has unsafe artifact")
    return result


def _copy_inventory(source: Path, destination: Path, inventory: Mapping[str, Mapping[str, Any]]) -> None:
    for relative, metadata in inventory.items():
        target = destination / relative
        if metadata == {"directory": True}:
            target.mkdir(exist_ok=False)
        else:
            _new_file(target, _stable_bytes(source / relative))


def _read_json(path: Path, label: str) -> dict[str, Any]:
    raw = _stable_bytes(path)
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"HANNA Sol lifecycle admission {label} is invalid") from error
    if not isinstance(value, dict) or _canonical(value) != raw:
        raise ValueError(f"HANNA Sol lifecycle admission {label} must be an object")
    return value


def _event(execution: ModuleType, source: Path, row: Mapping[str, Any]) -> dict[str, Any]:
    receipt = _read_json(source / "execution-receipt.json", "source receipt")
    return {
        "cell": dict(row), "identity": receipt.get("identity"),
        "native_request_bytes": _stable_bytes(source / "prompt-request.bin"),
        "outbound_payload": _stable_bytes(source / "predecessor-payload.json"),
        "effective_settings": {"route_name": row["route"]["route_name"], "effective_model": row["route"]["effective_model"], "requested_reasoning_effort": row["route"]["requested_reasoning_effort"], "tools_enabled": False, "web_search_enabled": False, "subagents_enabled": False, "output_schema_sha256": row["response_schema_sha256"], "provider_attested": False, "source": "codex_cli_local_events_and_invocation_v1"},
    }


def _verify_historical_lifecycle(execution: ModuleType, *, source_execution_root: Path, cell_id: str,
                                 frozen_successor_path: Path, hanna_csv_path: Path) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    source = source_execution_root / cell_id
    predecessor = execution._load_predecessor()
    schedule = predecessor.derive_schedule(frozen_successor_path=Path(frozen_successor_path), hanna_csv_path=Path(hanna_csv_path))
    rows = [dict(row) for row in schedule["mandatory_development"] if row["cell_id"] == cell_id]
    if len(rows) != 1 or rows[0]["route_name"] != "sol_validation":
        raise ValueError("HANNA Sol lifecycle admission accepts one frozen Sol validation cell")
    row, before = rows[0], _inventory(source)
    execution._validate_completed_inventory(source, is_sol=True)
    prepared, receipt, effective = (_read_json(source / name, name) for name in ("prepared.json", "execution-receipt.json", "effective-settings.json"))
    route_evidence = prepared.get("route_evidence")
    historical_route = {"codex_command": [prepared.get("executable")], "codex_cli_version": effective.get("codex_cli_version"), "codex_command_identity": effective.get("codex_command_identity")}
    if not isinstance(route_evidence, dict) or not isinstance(prepared.get("executable"), str):
        raise ValueError("HANNA Sol lifecycle admission historical route evidence is absent")
    original = execution.validate_live_sol_route
    execution.validate_live_sol_route = lambda _queue, broker_factory=None: (historical_route, dict(route_evidence))
    try:
        outcome = execution.verify_predecessor_receipt(_event(execution, source, row), execution_root=source_execution_root,
            queue_root=source_execution_root / ".historical-no-broker", frozen_successor_path=Path(frozen_successor_path), hanna_csv_path=Path(hanna_csv_path))
    finally:
        execution.validate_live_sol_route = original
    expected = {"accepted": False, "local_lifecycle_verified": True, "native_endpoint_contact_cardinality": "unproven", "reason": "local_codex_thread_events_do_not_attest_native_endpoint_contact_cardinality"}
    if outcome != expected or _inventory(source) != before:
        raise ValueError("HANNA Sol lifecycle admission historical receipt replay drifted")
    return row, receipt, before


def _overlaps(left: Path, right: Path) -> bool:
    try:
        return os.path.commonpath((os.path.normcase(os.fspath(left)), os.path.normcase(os.fspath(right)))) in {os.path.normcase(os.fspath(left)), os.path.normcase(os.fspath(right))}
    except ValueError:
        return False


def _remove_stage(stage: Path) -> None:
    if stage.exists():
        shutil.rmtree(stage)


def _clone_inventory(inventory: Mapping[str, Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    clone = dict(inventory)
    result = clone.pop(RESULT_NAME, None)
    if result is None or not isinstance(result.get("bytes"), int) or not isinstance(result.get("sha256"), str):
        raise ValueError("HANNA Sol lifecycle admission clone inventory lacks its result")
    return clone


def _deduplication_key(value: Any) -> dict[str, str]:
    if not isinstance(value, dict) or set(value) != DEDUPLICATION_FIELDS or any(not isinstance(entry, str) or not entry for entry in value.values()):
        raise ValueError("HANNA Sol lifecycle admission deduplication identity is incomplete")
    return dict(value)


def _source_deduplication_key(source: Path, receipt: Mapping[str, Any]) -> dict[str, str]:
    identity = receipt.get("identity")
    if (not isinstance(identity, dict) or not isinstance(receipt.get("cell_id"), str)
            or not isinstance(identity.get("contact_id"), str) or not isinstance(identity.get("session_id"), str)):
        raise ValueError("HANNA Sol lifecycle admission authenticated source identity is incomplete")
    return _deduplication_key({"cell_id": receipt["cell_id"], "contact_id": identity["contact_id"],
        "session_id": identity["session_id"], "request_sha256": _sha(_stable_bytes(source / "prompt-request.bin")),
        "final_response_sha256": _sha(_stable_bytes(source / "raw-codex-final-response.bin"))})


def _validate_prior_proof(path: Path, *, execution: ModuleType, frozen_successor_path: Path,
                          hanna_csv_path: Path) -> dict[str, Any]:
    proof = _read_json(Path(path), "prior proof")
    if (set(proof) != PROOF_FIELDS or proof.get("format_version") != 1 or proof.get("study_id") != STUDY_ID
            or proof.get("kind") != "sol_local_lifecycle_admission_proof" or proof.get("provider_calls_made") != 0
            or proof.get("provider_attested") is not False
            or proof.get("exec_v3_executor_sha256") != EXEC_SHA256
            or proof.get("exec_v3_contract_sha256") != EXEC_CONTRACT_SHA256
            or proof.get("admit_py_sha256") != _sha(_stable_bytes(Path(__file__)))
            or proof.get("admission_contract_sha256") != _sha(_stable_bytes(CONTRACT_PATH))
            or proof.get("evidence_status") != "local_lifecycle_verified_native_endpoint_contact_cardinality_unproven"):
        raise ValueError("HANNA Sol lifecycle admission prior proof identity drifted")
    key = _deduplication_key(proof.get("deduplication_key"))
    if proof.get("cell_id") != key["cell_id"]:
        raise ValueError("HANNA Sol lifecycle admission prior proof cell/deduplication identity drifted")
    if any(not isinstance(proof.get(field), str) or not proof[field] for field in ("source_execution_root", "source_cell_root", "destination_root", "source_receipt_sha256", "destination_result_sha256")):
        raise ValueError("HANNA Sol lifecycle admission prior proof path or hash is invalid")
    source_root, source_cell, destination = (_absolute(Path(proof[field])) for field in ("source_execution_root", "source_cell_root", "destination_root"))
    if (source_cell != source_root / key["cell_id"] or not isinstance(proof.get("source_inventory"), dict)
            or not isinstance(proof.get("destination_inventory"), dict)):
        raise ValueError("HANNA Sol lifecycle admission prior proof roots or inventories are invalid")
    source_inventory, destination_inventory = _inventory(source_cell), _inventory(destination)
    if source_inventory != proof["source_inventory"] or destination_inventory != proof["destination_inventory"]:
        raise ValueError("HANNA Sol lifecycle admission prior proof inventory drifted")
    if _clone_inventory(destination_inventory) != source_inventory:
        raise ValueError("HANNA Sol lifecycle admission prior proof destination is not an exact source clone")
    replay_row, receipt, replay_inventory = _verify_historical_lifecycle(execution, source_execution_root=source_root,
        cell_id=key["cell_id"], frozen_successor_path=Path(frozen_successor_path), hanna_csv_path=Path(hanna_csv_path))
    authenticated_key = _source_deduplication_key(source_cell, receipt)
    if (replay_row.get("cell_id") != proof.get("cell_id") or replay_inventory != source_inventory
            or proof.get("cell_id") != key["cell_id"] or key != authenticated_key):
        raise ValueError("HANNA Sol lifecycle admission prior proof deduplication key drifted")
    result = _read_json(destination / RESULT_NAME, "prior destination result")
    if (set(result) != RESULT_FIELDS or result.get("format_version") != 1 or result.get("study_id") != STUDY_ID
            or result.get("kind") != "sol_local_lifecycle_admission_result" or result.get("cell_id") != key["cell_id"]
            or result.get("state") != "local_lifecycle_verified" or result.get("provider_calls_made") != 0
            or result.get("provider_attested") is not False or result.get("native_contact_proven") is not False
            or result.get("native_endpoint_contact_cardinality") != "unproven"
            or result.get("evidence_status") != proof["evidence_status"]
            or result.get("source_receipt_sha256") != _sha(_canonical(receipt))
            or _deduplication_key(result.get("deduplication_key")) != authenticated_key
            or proof.get("source_receipt_sha256") != _sha(_canonical(receipt))
            or proof.get("destination_result_sha256") != _sha(_stable_bytes(destination / RESULT_NAME))):
        raise ValueError("HANNA Sol lifecycle admission prior proof result bindings drifted")
    return proof


def _prior_duplicate(paths: Iterable[Path], key: Mapping[str, Any], *, execution: ModuleType,
                     frozen_successor_path: Path, hanna_csv_path: Path) -> None:
    for path in paths:
        proof = _validate_prior_proof(Path(path), execution=execution,
            frozen_successor_path=Path(frozen_successor_path), hanna_csv_path=Path(hanna_csv_path))
        if proof.get("deduplication_key") == key:
            raise ValueError("HANNA Sol lifecycle admission deduplication key already admitted")


def admit_local_lifecycle(*, source_execution_root: Path, output_root: Path, proof_path: Path, cell_id: str,
                          frozen_successor_path: Path, hanna_csv_path: Path,
                          prior_proof_paths: Iterable[Path] = ()) -> dict[str, Any]:
    """Create a provider-free descendant while retaining the endpoint-contact ceiling."""
    contract()
    execution = _load_execution()
    source_execution_root, output_root, proof_path = map(_absolute, (Path(source_execution_root), Path(output_root), Path(proof_path)))
    source = source_execution_root / cell_id
    destination = output_root / cell_id
    for path in (source_execution_root, output_root.parent, proof_path.parent):
        _plain_ancestry(path, include_leaf=True)
    if any(_overlaps(source, target) for target in (output_root, destination, proof_path)):
        raise ValueError("HANNA Sol lifecycle admission source and destination must be disjoint")
    if output_root.exists() or destination.exists() or proof_path.exists():
        raise ValueError("HANNA Sol lifecycle admission refuses existing output, proof collision, or partial destination")
    row, receipt, source_inventory = _verify_historical_lifecycle(execution, source_execution_root=source_execution_root,
        cell_id=cell_id, frozen_successor_path=Path(frozen_successor_path), hanna_csv_path=Path(hanna_csv_path))
    key = _source_deduplication_key(source, receipt)
    if key["cell_id"] != cell_id:
        raise ValueError("HANNA Sol lifecycle admission receipt/cell identity drifted")
    _prior_duplicate(prior_proof_paths, key, execution=execution,
        frozen_successor_path=Path(frozen_successor_path), hanna_csv_path=Path(hanna_csv_path))
    stage = output_root.with_name(f".{output_root.name}.admission-stage-{uuid.uuid4().hex}")
    if stage.exists():
        raise ValueError("HANNA Sol lifecycle admission staging collision")
    stage.mkdir(parents=False)
    try:
        stage_destination = stage / cell_id
        stage_destination.mkdir()
        _copy_inventory(source, stage_destination, source_inventory)
        result = {"format_version": 1, "study_id": STUDY_ID, "kind": "sol_local_lifecycle_admission_result", "cell_id": cell_id,
                  "state": "local_lifecycle_verified", "provider_calls_made": 0, "provider_attested": False,
                  "native_endpoint_contact_cardinality": "unproven", "native_contact_proven": False,
                  "evidence_status": "local_lifecycle_verified_native_endpoint_contact_cardinality_unproven",
                  "source_receipt_sha256": _sha(_canonical(receipt)), "deduplication_key": key}
        _new_file(stage_destination / "result.json", _canonical(result))
        staged_inventory = _inventory(stage_destination)
        if _clone_inventory(staged_inventory) != source_inventory:
            raise ValueError("HANNA Sol lifecycle admission staged clone drifted from its initial source inventory")
        output_root.mkdir(parents=False)
        destination.mkdir()
        _copy_inventory(stage_destination, destination, staged_inventory)
        destination_inventory = _inventory(destination)
        if destination_inventory != staged_inventory or _clone_inventory(destination_inventory) != source_inventory:
            raise ValueError("HANNA Sol lifecycle admission destination bytes drifted from staging")
        if _inventory(source) != source_inventory:
            raise ValueError("HANNA Sol lifecycle admission source mutated during admission")
        proof = {"format_version": 1, "study_id": STUDY_ID, "kind": "sol_local_lifecycle_admission_proof", "provider_calls_made": 0,
                 "cell_id": cell_id, "source_execution_root": str(source_execution_root), "source_cell_root": str(source), "destination_root": str(destination),
                 "exec_v3_executor_sha256": EXEC_SHA256, "exec_v3_contract_sha256": EXEC_CONTRACT_SHA256,
                 "admit_py_sha256": _sha(_stable_bytes(Path(__file__))), "admission_contract_sha256": _sha(_stable_bytes(CONTRACT_PATH)),
                 "source_inventory": source_inventory, "destination_inventory": destination_inventory,
                 "source_receipt_sha256": _sha(_canonical(receipt)), "destination_result_sha256": _sha(_stable_bytes(destination / "result.json")),
                 "deduplication_key": key, "evidence_status": "local_lifecycle_verified_native_endpoint_contact_cardinality_unproven", "provider_attested": False}
        raw_proof = _canonical(proof)
        if (_inventory(source) != source_inventory or _inventory(destination) != destination_inventory
                or _clone_inventory(destination_inventory) != source_inventory):
            raise ValueError("HANNA Sol lifecycle admission artifacts changed before proof publication")
        _new_file(proof_path, raw_proof)
        if (_stable_bytes(proof_path) != raw_proof or _inventory(source) != source_inventory
                or _inventory(destination) != destination_inventory
                or _clone_inventory(destination_inventory) != source_inventory):
            raise ValueError("HANNA Sol lifecycle admission terminal artifact drift")
    except BaseException:
        if not output_root.exists():
            _remove_stage(stage)
        raise
    _remove_stage(stage)
    return {"accepted": True, "provider_calls_made": 0, "cell_id": cell_id, "destination_root": str(destination), "proof_path": str(proof_path), "evidence_status": "local_lifecycle_verified_native_endpoint_contact_cardinality_unproven"}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--admit-local-lifecycle", action="store_true")
    parser.add_argument("--source-execution-root", type=Path); parser.add_argument("--output-root", type=Path)
    parser.add_argument("--proof-path", type=Path); parser.add_argument("--cell-id")
    parser.add_argument("--frozen-successor-path", type=Path); parser.add_argument("--hanna-csv-path", type=Path)
    parser.add_argument("--prior-proof", type=Path, action="append", default=[])
    args = parser.parse_args(argv)
    if not args.admit_local_lifecycle or any(value is None for value in (args.source_execution_root, args.output_root, args.proof_path, args.cell_id, args.frozen_successor_path, args.hanna_csv_path)):
        parser.error("--admit-local-lifecycle and all root, proof, frozen, csv, and cell arguments are required")
    print(_canonical(admit_local_lifecycle(source_execution_root=args.source_execution_root, output_root=args.output_root, proof_path=args.proof_path, cell_id=args.cell_id, frozen_successor_path=args.frozen_successor_path, hanna_csv_path=args.hanna_csv_path, prior_proof_paths=args.prior_proof)).decode("utf-8"), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
