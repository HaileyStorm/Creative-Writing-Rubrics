#!/usr/bin/env python3
"""Freeze two Sol replacement descendants without reopening their terminal roots."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import stat
from types import ModuleType
from typing import Any, Mapping


STUDY_ID = "hbq-human-alignment-optimizer-v4-sol-replacement-schedule-v1"
DOCUMENTS = Path.home() / "Documents"
V4_EXECUTOR = Path(__file__).resolve().parents[1] / "hbq-human-alignment-optimizer-v4-native-subscription-v1" / "executor.py"
V4_CONTRACT = V4_EXECUTOR.with_name("study-contract.json")
V4_EXECUTOR_SHA256 = "6d93f69216d62bd0847aa6b338b6e2360587c82608669f78fbad245a34ba1c49"
V4_CONTRACT_SHA256 = "aac0c8952894a2501bd364fcf7fff392399633de8f310be1b97108061e78bbe9"
FROZEN_SUCCESSOR = DOCUMENTS / "cwr-hanna-successor-fresh88-freeze-v4" / "frozen-successor-contract.json"
HANNA_CSV = DOCUMENTS / "cwr-hanna-pinned-data-282f275" / "hanna_stories_annotations.csv"


def canonical(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _plain(path: Path, *, directory: bool = False) -> None:
    info = os.lstat(path)
    if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400):
        raise ValueError(f"HANNA Sol replacement path is reparsed: {path}")
    if directory != stat.S_ISDIR(info.st_mode):
        raise ValueError(f"HANNA Sol replacement path type drifted: {path}")


def stable_bytes(path: Path) -> bytes:
    path = Path(os.path.abspath(path))
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current /= part
        _plain(current, directory=current != path)
    before = os.lstat(path)
    with path.open("rb") as handle:
        opened = os.fstat(handle.fileno())
        raw = handle.read()
        after = os.fstat(handle.fileno())
    if (before.st_dev, before.st_ino, before.st_size) != (opened.st_dev, opened.st_ino, opened.st_size) or (opened.st_dev, opened.st_ino, opened.st_size) != (after.st_dev, after.st_ino, after.st_size):
        raise ValueError(f"HANNA Sol replacement file changed during read: {path}")
    return raw


def _inventory(root: Path) -> dict[str, dict[str, Any]]:
    _plain(root, directory=True)
    result: dict[str, dict[str, Any]] = {}
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        _plain(path, directory=path.is_dir())
        if path.is_dir():
            result[relative] = {"directory": True}
        else:
            raw = stable_bytes(path)
            result[relative] = {"bytes": len(raw), "sha256": sha256(raw)}
    return result


def _v4_schedule() -> dict[str, Any]:
    source, contract = stable_bytes(V4_EXECUTOR), stable_bytes(V4_CONTRACT)
    if sha256(source) != V4_EXECUTOR_SHA256 or sha256(contract) != V4_CONTRACT_SHA256:
        raise ValueError("HANNA Sol replacement pinned v4 schedule bytes drifted")
    module = ModuleType("_hanna_v4_pinned_schedule")
    module.__file__ = str(V4_EXECUTOR)
    exec(compile(source, str(V4_EXECUTOR), "exec"), module.__dict__)
    result = module.derive_schedule(frozen_successor_path=FROZEN_SUCCESSOR, hanna_csv_path=HANNA_CSV)
    if sha256(stable_bytes(V4_EXECUTOR)) != V4_EXECUTOR_SHA256:
        raise ValueError("HANNA Sol replacement v4 schedule changed during load")
    return result


TERMINALS = {
    "v4-cell-2eb4f20b3db15aac": {
        "root": DOCUMENTS / "cwr-hanna-v4-native-pilot-f22bf26" / "v4-cell-2eb4f20b3db15aac",
        "inventory": {
            "authorization-acknowledgement.json": {"bytes": 925, "sha256": "affec6b428dff996def9a5014163b31b05afeb89f5c248de6d0aa7616a691895"},
            "disclosure.json": {"bytes": 9580, "sha256": "4ebd49ed5d3fb569da0b85778617367bb086efd1d6fcfb43fe477fab6b237ed9"},
            "launch-intent.json": {"bytes": 297, "sha256": "f28d2bb462d57e56e9d414ee30e4c9a32b070da45cf3aa2fadacceabcf732972"},
            "predecessor-payload.json": {"bytes": 13630, "sha256": "8c225614f0b36559a17e37f40fd72b54ebec332911fa75979719720662ee9bfe"},
            "prepared.json": {"bytes": 3057, "sha256": "de0147af0674c2e0bcae8b30d56b87b75e88dc9586a2ac0789471e36573e87d0"},
            "prompt-request.bin": {"bytes": 6430, "sha256": "1559da913ef40e7fff06317a034bb8d9be4893ae4cf4583549a017fd477cb7ea"},
            "response-schema.json": {"bytes": 1364, "sha256": "38fb4d0c4c2f491542ea328c15cb5253da954321121229cd54a5936559a4c096"},
            "responses": {"directory": True}, "responses/batch-0001.attempt-0001.events.jsonl": {"bytes": 2276, "sha256": "2bf9adc1ed04ee8f6d42c8d1c9c4cfa069faf6563376c38eeb1c5ca170f4e863"},
            "responses/batch-0001.attempt-0001.message.json": {"bytes": 1645, "sha256": "e8fe3dc9f22a37a0fe711e8e52d86140e37a719e4c83c33c9094b816526c31bc"},
            "result.json": {"bytes": 300, "sha256": "991d2ab38195710c03707344e921b9866a55454a5d60b9740bc44297427ce013"},
            "zero-charge-route-proof.json": {"bytes": 1914, "sha256": "bc5559a33a03c463cbaf11c053b0553414e25f4b38d90cbb88beb816d00a7f28"},
        },
    },
    "v4-cell-2333370999fb84f3": {
        "root": DOCUMENTS / "cwr-hanna-v4-native-pilot-8afd547-v2" / "v4-cell-2333370999fb84f3",
        "inventory": {
            "authorization-acknowledgement.json": {"bytes": 925, "sha256": "21aae6aa65e6eca9190d0ab39c070a4112ee5b4ba04e613ee518c872ffd304cc"},
            "disclosure.json": {"bytes": 8441, "sha256": "086c6168d54d4046105ffb7c6092dcca2485b8b1e0e72ad16a66610905e90b7c"},
            "launch-intent.json": {"bytes": 297, "sha256": "24f8b1beed0002548af9dc3411969fbc26928655530cbacd4213ef1cc251fa9b"},
            "predecessor-payload.json": {"bytes": 11343, "sha256": "d74dd59c90555440c1e8467db2ae37d90bc9867ff422dbd6b0024000333cbb83"},
            "prepared.json": {"bytes": 3057, "sha256": "f5ac8d890662b0286825afbbd4e4831f531598efe2f4df6b134aed660a7fb2cf"},
            "prompt-request.bin": {"bytes": 5328, "sha256": "5307cfc3c41d141ff7c51eb931227252afbe7291d036dbdacf7bb4bd0d0cff6b"},
            "response-schema.json": {"bytes": 1364, "sha256": "38fb4d0c4c2f491542ea328c15cb5253da954321121229cd54a5936559a4c096"},
            "responses": {"directory": True}, "responses/batch-0001.attempt-0001.events.jsonl": {"bytes": 2085, "sha256": "5ba62793946b3b64823f1a031c8e494e1a1af29b4c5e48d65218c2d761167310"},
            "responses/batch-0001.attempt-0001.message.json": {"bytes": 1688, "sha256": "9b15b6f7cd439bb95b9e81766a1ad96703c145296b53698c89610f1a27d900dc"},
            "result.json": {"bytes": 300, "sha256": "67acc04ca8f552f5e68a883411f68217c6268287d5a68a16529e40ff7af2128d"},
            "zero-charge-route-proof.json": {"bytes": 1914, "sha256": "4d00ab1cf494c2fd002d9e47c27feefdb4fc83badbc65dfb3139fc4ccb068c23"},
        },
    },
}

ADMISSIONS = {
    "v4-cell-bfe6152248d26a49": {"proof": DOCUMENTS / "cwr-hanna-v4-native-admission-proof-f22bf26-v4-cell-bfe6152248d26a49.json", "proof_sha256": "3ff5a918f2ab84722b598ea0d202e4415607eb7972298f073f91d256b55b06b8"},
    "v4-cell-a903ff8203f0054c": {"proof": DOCUMENTS / "cwr-hanna-v4-native-admission-proof-f22bf26-v4-cell-a903ff8203f0054c.json", "proof_sha256": "9d2a95b2d6c67f3571c8683c95cbab5aef8ac0fdd165895104cbb834e8ac15a1"},
}


def _json(path: Path, label: str, *, canonical_required: bool = True) -> dict[str, Any]:
    try:
        value = json.loads(stable_bytes(path).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"HANNA Sol replacement {label} is not strict JSON") from error
    if not isinstance(value, dict) or (canonical_required and canonical(value) != stable_bytes(path)):
        raise ValueError(f"HANNA Sol replacement {label} is not canonical JSON")
    return value


def derive_replacements() -> list[dict[str, Any]]:
    v4 = _v4_schedule()
    rows: list[dict[str, Any]] = []
    for terminal_cell, terminal in TERMINALS.items():
        root = Path(terminal["root"])
        if _inventory(root) != terminal["inventory"]:
            raise ValueError("HANNA Sol replacement terminal-root inventory/hash drifted")
        result = _json(root / "result.json", "terminal result")
        prepared = _json(root / "prepared.json", "terminal preparation")
        if result != {"cell_id": terminal_cell, "error_type": "_ProviderAttemptFailure", "format_version": 1, "kind": "native_exec_result", "native_contact_proven": False, "process_launches": 1, "state": "reconcile_required_after_process_launch", "study_id": prepared["study_id"]}:
            raise ValueError("HANNA Sol replacement predecessor is not the pinned terminal failure")
        original = [row for row in v4["mandatory_development"] if row["cell_id"] == terminal_cell]
        if len(original) != 1 or original[0]["route_name"] != "sol_validation":
            raise ValueError("HANNA Sol replacement original terminal cell is not one pinned Sol slot")
        original = original[0]
        candidates = sorted(
            (row for row in v4["mandatory_development"] if row["route_name"] == "grok_primary"
             and row["partition"] == "development" and row["candidate_id"] == original["candidate_id"]
             and row["prompt_group_id"] == original["prompt_group_id"]),
            key=lambda row: row["item_id"],
        )
        used_sol_items = {row["item_id"] for row in v4["mandatory_development"] if row["route_name"] == "sol_validation"
                          and row["candidate_id"] == original["candidate_id"] and row["prompt_group_id"] == original["prompt_group_id"]}
        next_rows = [row for row in candidates if row["item_id"] > original["item_id"] and row["item_id"] not in used_sol_items]
        if not next_rows:
            raise ValueError("HANNA Sol replacement has no next unused same-group development item")
        grok = next_rows[0]
        if (grok["candidate_id"] != original["candidate_id"] or grok["prompt_group_id"] != original["prompt_group_id"]
                or grok["item_id"] == original["item_id"] or grok["item_id"] in used_sol_items):
            raise ValueError("HANNA Sol replacement descendant geometry drifted")
        admission = ADMISSIONS.get(grok["cell_id"])
        if admission is None:
            raise ValueError("HANNA Sol replacement selected next Grok cell lacks an admitted proof")
        proof_path = Path(admission["proof"])
        raw_proof = stable_bytes(proof_path)
        if sha256(raw_proof) != admission["proof_sha256"]:
            raise ValueError("HANNA Sol replacement Grok admission proof drifted")
        proof = _json(proof_path, "Grok admission proof")
        destination = Path(proof.get("destination_root", ""))
        if (proof.get("kind") != "completed_grok_admission_proof" or proof.get("cell_id") != grok["cell_id"]
                or proof.get("provider_calls_made") != 0 or _inventory(destination) != proof.get("destination_inventory")):
            raise ValueError("HANNA Sol replacement Grok admission binding drifted")
        grok_prepared = _json(destination / "prepared.json", "admitted Grok preparation")
        grok_cell = grok_prepared.get("cell")
        if not isinstance(grok_cell, dict) or any(grok_cell.get(key) != grok[key] for key in ("item_id", "candidate_id", "prompt_group_id", "parent_cell_id", "cell_id")):
            raise ValueError("HANNA Sol replacement selected next Grok mapping drifted")
        task, schema = stable_bytes(destination / "native-request.bin"), stable_bytes(destination / "outbound-payload.json")
        payload = _json(destination / "outbound-payload.json", "admitted Grok payload", canonical_required=False)
        components = payload.get("components")
        if (not isinstance(components, dict) or task != components.get("task_payload", "").encode("utf-8")
                or sha256(task) != grok_cell.get("task_payload_sha256")
                or sha256(components.get("response_schema", "").encode("utf-8")) != grok_cell.get("response_schema_sha256")):
            raise ValueError("HANNA Sol replacement admitted Grok prompt/schema drifted")
        key = {"terminal_cell_id": terminal_cell, "grok_cell_id": grok["cell_id"], "parent_cell_id": grok["parent_cell_id"], "task_payload_sha256": sha256(task)}
        replacement_id = "v4-sol-replacement-" + sha256(canonical(key))[:16]
        rows.append({"cell_id": replacement_id, "route_name": "sol_validation", "replacement_for_terminal_cell_id": terminal_cell,
                     "matched_grok_cell_id": grok["cell_id"], "parent_cell_id": grok["parent_cell_id"], "item_id": grok["item_id"],
                     "original_item_id": original["item_id"], "candidate_id": original["candidate_id"], "prompt_group_id": original["prompt_group_id"],
                     "selection_rule": "lexicographically_next_unused_same_candidate_same_prompt_group_development_grok_item",
                     "task_payload_sha256": sha256(task), "response_schema_sha256": grok_cell["response_schema_sha256"],
                     "grok_admission_proof_sha256": admission["proof_sha256"], "grok_destination_root": str(destination),
                     "terminal_inventory_sha256": sha256(canonical(terminal["inventory"])), "replacement_key_sha256": sha256(canonical(key))})
    if len({row["cell_id"] for row in rows}) != 2:
        raise ValueError("HANNA Sol replacement IDs are not unique")
    return rows
