"""Provider-free, one-cell admission of a verified exec-v1 Grok receipt."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import uuid
from pathlib import Path
from types import ModuleType
from typing import Any, Callable, Mapping


HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
STUDY_ID = "hbq-human-alignment-optimizer-v4-native-admission-v1"
CONTRACT_PATH = HERE / "study-contract.json"
CONTRACT_SHA256 = "43f8bdab947a360224d5f9c02d0e69f5dd98fc261bc8d5e94dc17fc9997f92e8"
EXEC_PATH = HERE.parent / "hbq-human-alignment-optimizer-v4-native-subscription-exec-v1" / "executor.py"
PREDECESSOR_PATH = HERE.parent / "hbq-human-alignment-optimizer-v4-native-subscription-v1" / "executor.py"
PREDECESSOR_CONTRACT_PATH = HERE.parent / "hbq-human-alignment-optimizer-v4-native-subscription-v1" / "study-contract.json"
EXEC_SHA256 = "5d2bd6871fe2013b8af5e166d89eeb020ff98889ce30494dd8889f7bee2d942f"
PREDECESSOR_SHA256 = "6d93f69216d62bd0847aa6b338b6e2360587c82608669f78fbad245a34ba1c49"
PREDECESSOR_CONTRACT_SHA256 = "aac0c8952894a2501bd364fcf7fff392399633de8f310be1b97108061e78bbe9"
BASE_FILES = frozenset({
    "outbound-payload.json", "disclosure.json", "acknowledgement.json",
    "zero-charge-route-proof.json", "prepared.json",
})
SETTLED_FILES = frozenset({
    "intent.json", "native-request.bin", "native-response.bin", "effective-settings.json", "result.json",
})
DESTINATION_FILES = BASE_FILES | SETTLED_FILES


def _sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _canonical(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _absolute(path: Path) -> Path:
    return Path(os.path.abspath(os.fspath(path)))


def _reject_reparse(path: Path, info: os.stat_result) -> None:
    if stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)):
        raise ValueError(f"HANNA admission reparse point is forbidden: {path}")


def _assert_plain_ancestry(path: Path, *, include_leaf: bool) -> None:
    absolute = _absolute(path)
    anchor = Path(absolute.anchor)
    parts = absolute.parts[1:]
    limit = len(parts) if include_leaf else len(parts) - 1
    current = anchor
    for part in parts[:limit]:
        current = current / part
        try:
            _reject_reparse(current, os.lstat(current))
        except OSError as error:
            raise ValueError(f"HANNA admission path is unavailable: {current}") from error


def _stable_bytes(path: Path) -> bytes:
    path = _absolute(path)
    _assert_plain_ancestry(path, include_leaf=True)
    before = os.lstat(path)
    if not stat.S_ISREG(before.st_mode):
        raise ValueError(f"HANNA admission requires regular file: {path}")
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        opened = os.fstat(descriptor)
        before_path_identity = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
        opened_path_identity = (opened.st_dev, opened.st_ino, opened.st_size, opened.st_mtime_ns)
        opened_handle_identity = (*opened_path_identity, opened.st_ctime_ns)
        if before_path_identity != opened_path_identity:
            raise ValueError(f"HANNA admission file identity drifted: {path}")
        chunks: list[bytes] = []
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
        after_open = os.fstat(descriptor)
        after_path = os.lstat(path)
        after_handle_identity = (after_open.st_dev, after_open.st_ino, after_open.st_size, after_open.st_mtime_ns, after_open.st_ctime_ns)
        after_path_identity = (after_path.st_dev, after_path.st_ino, after_path.st_size, after_path.st_mtime_ns)
        if opened_handle_identity != after_handle_identity or before_path_identity != after_path_identity:
            raise ValueError(f"HANNA admission file changed during read: {path}")
        return b"".join(chunks)
    finally:
        os.close(descriptor)


def _new_file(path: Path, value: bytes) -> None:
    _assert_plain_ancestry(path.parent, include_leaf=True)
    try:
        with path.open("xb") as handle:
            handle.write(value)
            handle.flush()
            os.fsync(handle.fileno())
    except FileExistsError as error:
        raise ValueError(f"HANNA admission refuses to overwrite {path}") from error


def _load_verified_buffer(path: Path, raw: bytes, name: str) -> ModuleType:
    module = ModuleType(name)
    module.__file__ = str(path)
    exec(compile(raw, str(path), "exec"), module.__dict__)
    return module


def _load_pinned() -> tuple[ModuleType, ModuleType]:
    predecessor_raw = _stable_bytes(PREDECESSOR_PATH)
    execution_raw = _stable_bytes(EXEC_PATH)
    predecessor_contract_raw = _stable_bytes(PREDECESSOR_CONTRACT_PATH)
    if (_sha(predecessor_raw) != PREDECESSOR_SHA256 or _sha(execution_raw) != EXEC_SHA256
            or _sha(predecessor_contract_raw) != PREDECESSOR_CONTRACT_SHA256):
        raise ValueError("HANNA admission pinned dependency bytes drifted")
    predecessor = _load_verified_buffer(PREDECESSOR_PATH, predecessor_raw, "_hanna_admission_predecessor")
    execution = _load_verified_buffer(EXEC_PATH, execution_raw, "_hanna_admission_exec")
    if (getattr(execution, "PREDECESSOR_SHA256", None) != PREDECESSOR_SHA256
            or getattr(execution, "PREDECESSOR_CONTRACT_SHA256", None) != PREDECESSOR_CONTRACT_SHA256):
        raise ValueError("HANNA admission exec-v1 predecessor pin drifted")
    try:
        frozen_contract = json.loads(predecessor_contract_raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("HANNA admission predecessor contract buffer is invalid") from error
    predecessor.contract = lambda: dict(frozen_contract)
    return predecessor, execution


def contract() -> dict[str, Any]:
    raw = _stable_bytes(CONTRACT_PATH)
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("HANNA admission contract is invalid") from error
    expected = {
        "format_version": 1, "study_id": STUDY_ID, "kind": "provider_free_completed_grok_admission_descendant",
        "predecessor": {"study_id": "hbq-human-alignment-optimizer-v4-native-subscription-v1", "executor_sha256": PREDECESSOR_SHA256, "contract_sha256": PREDECESSOR_CONTRACT_SHA256},
        "native_exec": {"study_id": "hbq-human-alignment-optimizer-v4-native-subscription-exec-v1", "executor_sha256": EXEC_SHA256},
        "admission": {"accepted_route": "grok_primary", "provider_calls_made": 0, "source_root": "completed_exec_v1_cell_root", "destination_shape": "predecessor_native_returned_unprojected", "source_immutability": "required", "projection": "owned_by_predecessor", "clone_semantics": "identical_source_artifacts_are_same_evidence_and_require_downstream_contact_deduplication"},
    }
    if _sha(raw) != CONTRACT_SHA256 or value != expected:
        raise ValueError("HANNA admission contract identity drifted")
    return value


def _plain_inventory(root: Path, expected: frozenset[str] | None = None) -> dict[str, dict[str, Any]]:
    _assert_plain_ancestry(root, include_leaf=True)
    try:
        entries = list(os.scandir(root))
    except OSError as error:
        raise ValueError("HANNA admission root is unavailable") from error
    names = {entry.name for entry in entries}
    if expected is not None and names != expected:
        raise ValueError("HANNA admission root inventory has missing, extra, or orphan artifacts")
    result: dict[str, dict[str, Any]] = {}
    for entry in entries:
        path = Path(entry.path)
        try:
            info = entry.stat(follow_symlinks=False)
        except OSError as error:
            raise ValueError("HANNA admission root inventory is unstable") from error
        _reject_reparse(path, info)
        if not stat.S_ISREG(info.st_mode):
            raise ValueError("HANNA admission root has non-regular artifact")
        raw = _stable_bytes(path)
        result[entry.name] = {"bytes": len(raw), "sha256": _sha(raw)}
    return dict(sorted(result.items()))


def _tree_inventory(root: Path) -> dict[str, dict[str, Any]]:
    """Bind the exec root's fixed response subdirectory without accepting links."""
    _assert_plain_ancestry(root, include_leaf=True)
    result: dict[str, dict[str, Any]] = {}
    for path in sorted(root.rglob("*"), key=lambda item: item.as_posix()):
        relative = path.relative_to(root).as_posix()
        info = os.lstat(path)
        _reject_reparse(path, info)
        if stat.S_ISDIR(info.st_mode):
            result[relative] = {"directory": True}
        elif stat.S_ISREG(info.st_mode):
            raw = _stable_bytes(path)
            result[relative] = {"bytes": len(raw), "sha256": _sha(raw)}
        else:
            raise ValueError("HANNA admission source root has an unsafe artifact")
    return result


def _read_canonical(predecessor: ModuleType, path: Path, label: str) -> dict[str, Any]:
    return predecessor._read_canonical(path, label=label)


def _historical_grok_receipt(*, execution: ModuleType, predecessor: ModuleType, source_root: Path, cell_id: str,
                             frozen_successor_path: Path, hanna_csv_path: Path) -> tuple[dict[str, Any], bytes, bytes, dict[str, Any], dict[str, Any]]:
    source_cell = source_root / cell_id
    source_before = _tree_inventory(source_cell)
    schedule = predecessor.derive_schedule(frozen_successor_path=frozen_successor_path, hanna_csv_path=hanna_csv_path)
    row = predecessor._cell(schedule, cell_id)
    if row["route_name"] != "grok_primary":
        raise ValueError("HANNA admission accepts completed Grok primary cells only")
    prepared, payload, task, schema, fresh_row = execution._read_prepared(
        predecessor, source_cell, cell_id=cell_id, frozen_successor_path=frozen_successor_path,
        hanna_csv_path=hanna_csv_path, require_pristine=False,
    )
    if fresh_row != row:
        raise ValueError("HANNA admission source row is relabelled")
    expected_root = set(execution.PREPARED_FILES) | {
        "raw-grok-envelope.bin", "grok-record.json", "launch-intent.json", "effective-settings.json",
        "execution-receipt.json", "responses",
    }
    if set(source_before) != expected_root | {
        "responses/batch-0001.attempt-0001.prompt.txt", "responses/batch-0001.attempt-0001.grok.envelope.json",
    }:
        raise ValueError("HANNA admission source exec inventory is incomplete or contains orphan artifacts")
    if source_before["responses"] != {"directory": True}:
        raise ValueError("HANNA admission source responses directory is unsafe")
    receipt = _read_canonical(predecessor, source_cell / "execution-receipt.json", "admission source receipt")
    record = _read_canonical(predecessor, source_cell / "grok-record.json", "admission source Grok record")
    effective = _read_canonical(predecessor, source_cell / "effective-settings.json", "admission source effective settings")
    identity = receipt.get("identity")
    if not isinstance(identity, dict) or predecessor._validate_identity(identity, row) != identity:
        raise ValueError("HANNA admission source identity is absent")
    normalized_settings = {
        "route_name": row["route"]["route_name"], "effective_model": row["route"]["effective_model"],
        "requested_reasoning_effort": row["route"]["requested_reasoning_effort"], "tools_enabled": False,
        "web_search_enabled": False, "subagents_enabled": False,
        "output_schema_sha256": row["response_schema_sha256"], "provider_attested": False,
        "source": "grok_cli_invocation_and_envelope_v1",
    }
    response = _stable_bytes(source_cell / "raw-grok-envelope.bin")
    if response != _stable_bytes(source_cell / "responses" / "batch-0001.attempt-0001.grok.envelope.json"):
        raise ValueError("HANNA admission source envelope artifact is misassociated")
    if task != _stable_bytes(source_cell / "responses" / "batch-0001.attempt-0001.prompt.txt"):
        raise ValueError("HANNA admission source request artifact is misassociated")
    request_id, session_id = execution._envelope_identity(response, record)
    evidence = prepared.get("route_evidence")
    proof = _read_canonical(predecessor, source_cell / "zero-charge-route-proof.json", "admission source route proof")
    expected_effective_keys = {"requested_model", "reported_model", "requested_reasoning_effort", "reasoning_attested", "grok_cli_version", "grok_command_identity", "tool_free_argv", "system_prompt_override"}
    if (not isinstance(evidence, dict) or proof.get("route_evidence") != evidence or receipt.get("route_evidence") != evidence
            or prepared.get("route_status") != "GROK_PREPARED_NO_CONTACT" or prepared.get("requested") != {"model": "grok-4.6", "reasoning_effort": "high"}
            or set(effective) != expected_effective_keys or effective.get("requested_model") != "grok-4.6"
            or effective.get("reported_model") != "grok-4.6-build" or effective.get("requested_reasoning_effort") != "high"
            or effective.get("reasoning_attested") is not False or effective.get("grok_cli_version") != evidence.get("grok_cli_version")
            or execution._sha(execution._canonical(effective.get("grok_command_identity"))) != evidence.get("grok_command_identity_sha256")
            or effective.get("tool_free_argv") != execution.TOOL_FREE_ARGV or effective.get("system_prompt_override") != execution.SYSTEM_PROMPT
            or record.get("cli_version") != evidence.get("grok_cli_version") or record.get("requested") != {"model": "grok-4.6", "reasoning_effort": "high"}
            or record.get("reported") != {"provider": "grok", "model": "grok-4.6-build"} or record.get("reasoning_attested") is not False
            or receipt.get("study_id") != execution.STUDY_ID or receipt.get("kind") != "grok_native_envelope_receipt"
            or receipt.get("cell_id") != cell_id or receipt.get("native_contact_proven") is not True or receipt.get("process_launches") != 1
            or receipt.get("request_sha256") != execution._sha(task) or receipt.get("response_schema_sha256") != execution._sha(schema)
            or receipt.get("raw_envelope_sha256") != execution._sha(response) or receipt.get("effective_settings_sha256") != execution._sha(execution._canonical(effective))
            or receipt.get("identity") != identity or identity.get("contact_id") != request_id or identity.get("session_id") != session_id):
        raise ValueError("HANNA admission historical Grok receipt bindings drifted")
    intent = _read_canonical(predecessor, source_cell / "launch-intent.json", "admission source launch intent")
    expected_intent = {"format_version": 1, "study_id": execution.STUDY_ID, "kind": "process_launch_intent_not_native_contact", "cell_id": cell_id,
                       "prepared_sha256": execution._sha(execution._canonical(prepared)), "native_contact_proven": False}
    if intent != expected_intent or receipt.get("launch_intent_sha256") != execution._sha(execution._canonical(intent)):
        raise ValueError("HANNA admission source launch intent is misassociated")
    predecessor._validate_effective_settings(normalized_settings, row)
    if _tree_inventory(source_cell) != source_before:
        raise ValueError("HANNA admission source changed while being verified")
    return row, payload, task, normalized_settings, {
        "source_inventory": source_before, "identity": identity, "response": response,
        "receipt": receipt, "schema": schema, "evidence": evidence,
    }


def _destination_base(predecessor: ModuleType, row: Mapping[str, Any], schedule: Mapping[str, Any], payload: bytes) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    disclosure = predecessor._disclosure(row=row, schedule=schedule, payload=payload)
    acknowledgement = {
        "format_version": 1, "study_id": predecessor.STUDY_ID, "kind": "acknowledgement",
        "cell_id": row["cell_id"], "disclosure_sha256": predecessor.digest(disclosure), "acknowledged": True,
        "admission_source": STUDY_ID,
    }
    proof = {
        "format_version": 1, "study_id": predecessor.STUDY_ID, "kind": "zero_charge_route_proof",
        "cell_id": row["cell_id"], "disclosure_sha256": predecessor.digest(disclosure), "acknowledged": True,
        "route_descriptor_sha256": predecessor.digest(row["route"]), "account_class": "subscription",
        "zero_charge_only": True, "paid_fallback_forbidden": True, "api_fallback_forbidden": True,
        "admission_source": STUDY_ID,
    }
    prepared = predecessor._prepared(row=row, schedule=schedule, payload=payload, disclosure=disclosure,
                                     acknowledgement=acknowledgement, proof=proof)
    return disclosure, acknowledgement, proof, prepared


def _overlaps(left: Path, right: Path) -> bool:
    left_text, right_text = os.path.normcase(os.fspath(left)), os.path.normcase(os.fspath(right))
    try:
        common = os.path.commonpath((left_text, right_text))
    except ValueError:
        return False
    return common == left_text or common == right_text


def _reject_overlap(*, source_root: Path, source_cell: Path, output_root: Path, destination: Path,
                    proof_path: Path) -> None:
    sources = (source_root, source_cell)
    targets = (output_root, destination, proof_path)
    for left in sources:
        for right in targets:
            if _overlaps(left, right):
                raise ValueError("HANNA admission source, destination, and proof paths must not overlap")


def _remove_owned_root(root: Path) -> None:
    if not root.exists():
        return
    for child in root.iterdir():
        info = os.lstat(child)
        _reject_reparse(child, info)
        if stat.S_ISDIR(info.st_mode):
            _remove_owned_root(child)
        elif not stat.S_ISREG(info.st_mode):
            raise ValueError("HANNA admission refuses unsafe staging cleanup")
        else:
            child.unlink()
    root.rmdir()


def admit_completed_grok(*, source_execution_root: Path, output_root: Path, proof_path: Path,
                         cell_id: str, frozen_successor_path: Path,
                         hanna_csv_path: Path) -> dict[str, Any]:
    """Verify one finished exec-v1 Grok root and create a new immutable predecessor-shaped descendant."""
    contract()
    predecessor, execution = _load_pinned()
    source_execution_root, output_root, proof_path = map(_absolute, (Path(source_execution_root), Path(output_root), Path(proof_path)))
    _assert_plain_ancestry(source_execution_root, include_leaf=True)
    _assert_plain_ancestry(output_root.parent, include_leaf=True)
    _assert_plain_ancestry(proof_path.parent, include_leaf=True)
    destination = output_root / cell_id
    _reject_overlap(source_root=source_execution_root, source_cell=source_execution_root / cell_id,
                    output_root=output_root, destination=destination, proof_path=proof_path)
    if output_root.exists() or destination.exists() or proof_path.exists():
        raise ValueError("HANNA admission refuses existing destination, proof, copy, or partial output")
    row, payload, task, settings, source = _historical_grok_receipt(
        execution=execution, predecessor=predecessor, source_root=source_execution_root, cell_id=cell_id,
        frozen_successor_path=Path(frozen_successor_path), hanna_csv_path=Path(hanna_csv_path),
    )
    schedule = predecessor.derive_schedule(frozen_successor_path=Path(frozen_successor_path), hanna_csv_path=Path(hanna_csv_path))
    disclosure, acknowledgement, route_proof, prepared = _destination_base(predecessor, row, schedule, payload)
    intent = predecessor._expected_intent(row, prepared)
    result = {
        "format_version": 1, "study_id": predecessor.STUDY_ID, "kind": "native_subscription_cell_result",
        "state": "native_returned_unprojected", "cell_id": cell_id, "intent_sha256": predecessor.digest(intent),
        "native_request_sha256": predecessor.digest_bytes(task), "native_response_sha256": predecessor.digest_bytes(source["response"]),
        "effective_settings_sha256": predecessor.digest(settings), "identity": source["identity"],
        "identity_sha256": predecessor.digest(source["identity"]), "provider_calls_made": 1,
    }
    stage_root = output_root.with_name(f".{output_root.name}.admission-stage-{uuid.uuid4().hex}")
    if stage_root.exists():
        raise ValueError("HANNA admission staging path unexpectedly exists")
    stage_root.mkdir(parents=False, exist_ok=False)
    stage_destination = stage_root / cell_id
    stage_destination.mkdir(exist_ok=False)
    files = {
        "outbound-payload.json": payload, "disclosure.json": predecessor.canonical(disclosure),
        "acknowledgement.json": predecessor.canonical(acknowledgement),
        "zero-charge-route-proof.json": predecessor.canonical(route_proof), "prepared.json": predecessor.canonical(prepared),
        "intent.json": predecessor.canonical(intent), "native-request.bin": task,
        "native-response.bin": source["response"], "effective-settings.json": predecessor.canonical(settings),
        "result.json": predecessor.canonical(result),
    }
    reserved = False
    published = False
    proof_raw: bytes | None = None
    try:
        for name, value in files.items():
            _new_file(stage_destination / name, value)
        staged_inventory = _plain_inventory(stage_destination, DESTINATION_FILES)
        predecessor._validate_persisted_result(stage_destination, row=row, prepared=prepared, inventory_state="native_returned_unprojected")
        output_root.mkdir(parents=False, exist_ok=False)
        reserved = True
        destination.mkdir(exist_ok=False)
        for name, value in files.items():
            _new_file(destination / name, value)
        destination_inventory = _plain_inventory(destination, DESTINATION_FILES)
        if destination_inventory != staged_inventory:
            raise ValueError("HANNA admission reserved destination bytes drifted from exclusive staging")
        published = True
        predecessor._validate_persisted_result(destination, row=row, prepared=prepared, inventory_state="native_returned_unprojected")
        _remove_owned_root(stage_root)
        admit_raw = _stable_bytes(Path(__file__))
        contract_raw = _stable_bytes(CONTRACT_PATH)
        proof = {
            "format_version": 1, "study_id": STUDY_ID, "kind": "completed_grok_admission_proof",
            "provider_calls_made": 0, "cell_id": cell_id,
            "source_execution_root": str(source_execution_root), "source_cell_root": str(source_execution_root / cell_id),
            "source_exec_executor_sha256": EXEC_SHA256, "predecessor_executor_sha256": PREDECESSOR_SHA256,
            "predecessor_contract_sha256": PREDECESSOR_CONTRACT_SHA256,
            "admit_py_sha256": _sha(admit_raw), "admission_contract_sha256": _sha(contract_raw),
            "source_inventory": source["source_inventory"], "destination_root": str(destination),
            "destination_inventory": destination_inventory, "source_receipt_sha256": _sha(_canonical(source["receipt"])),
            "source_identity_sha256": predecessor.digest(source["identity"]),
            "native_request_sha256": _sha(task), "native_response_sha256": _sha(source["response"]),
            "destination_result_sha256": _sha(files["result.json"]),
            "deduplication_key": {"cell_id": cell_id, "contact_id": source["identity"]["contact_id"], "session_id": source["identity"]["session_id"], "native_request_sha256": _sha(task), "native_response_sha256": _sha(source["response"])},
        }
        proof_raw = _canonical(proof)
        if _plain_inventory(destination, DESTINATION_FILES) != destination_inventory or _tree_inventory(source_execution_root / cell_id) != source["source_inventory"]:
            raise ValueError("HANNA admission source or destination changed before proof publication")
        _new_file(proof_path, proof_raw)
        if (_plain_inventory(destination, DESTINATION_FILES) != destination_inventory
                or _tree_inventory(source_execution_root / cell_id) != source["source_inventory"]
                or _stable_bytes(proof_path) != proof_raw):
            raise ValueError("HANNA admission terminal artifacts changed after publication")
    except BaseException as error:
        if stage_root.exists():
            _remove_owned_root(stage_root)
        if published or reserved:
            raise RuntimeError("HANNA admission requires reconciliation after reserved destination change") from error
        raise error
    return {"accepted": True, "cell_id": cell_id, "provider_calls_made": 0,
            "destination_root": str(destination), "proof_path": str(proof_path)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--admit-completed-grok", action="store_true")
    parser.add_argument("--source-execution-root", type=Path)
    parser.add_argument("--output-root", type=Path)
    parser.add_argument("--proof-path", type=Path)
    parser.add_argument("--frozen-successor-path", type=Path)
    parser.add_argument("--hanna-csv-path", type=Path)
    parser.add_argument("--cell-id")
    args = parser.parse_args(argv)
    if not args.admit_completed_grok:
        parser.error("--admit-completed-grok is required")
    required = (args.source_execution_root, args.output_root, args.proof_path, args.frozen_successor_path,
                args.hanna_csv_path, args.cell_id)
    if any(value is None for value in required):
        parser.error("all admission root, frozen, csv, and cell arguments are required")
    result = admit_completed_grok(source_execution_root=args.source_execution_root, output_root=args.output_root,
                                  proof_path=args.proof_path, frozen_successor_path=args.frozen_successor_path,
                                  hanna_csv_path=args.hanna_csv_path, cell_id=args.cell_id)
    print(_canonical(result).decode("utf-8"), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
