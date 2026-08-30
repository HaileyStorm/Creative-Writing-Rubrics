"""Build a provider-free public manifest of authenticated Sol lifecycle admissions."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
from types import ModuleType
from typing import Any, Mapping


HERE = Path(__file__).resolve().parent
STUDY_ID = "hbq-human-alignment-optimizer-v4-sol-local-lifecycle-manifest-v1"
CONTRACT_PATH = HERE / "study-contract.json"
ADMISSION_PATH = HERE.parent / "hbq-human-alignment-optimizer-v4-sol-local-lifecycle-admission-v1" / "admit.py"
ADMISSION_CONTRACT_PATH = ADMISSION_PATH.with_name("study-contract.json")
ADMISSION_SHA256 = "d6ac8d8ac6ba4815ff37193b185e7c2cf741a20440c8c1a3b5beae04fc37e0c0"
ADMISSION_CONTRACT_SHA256 = "c14188ccd3cac43059030b7dfbecba507219ecb688e1c435376cc333afc0ea63"
FROZEN_SUCCESSOR_SHA256 = "b0f6dd24415c388a3104f8c9304ce301193cf0a48631a86c4886bc8ce48468e7"
HANNA_CSV_SHA256 = "ef59054d27fa32def06cfdc57243b1dd09c7e71f40b6d9d43fecfbf60e59026b"
TERMINAL_CELLS = frozenset({"v4-cell-2eb4f20b3db15aac", "v4-cell-2333370999fb84f3"})
EXPECTED_PROOF_COUNT = 33
RESULT_FIELDS = frozenset({"format_version", "study_id", "kind", "inputs", "counts", "ceiling", "cells"})
CELL_FIELDS = frozenset({"cell_id", "proof_sha256", "source_receipt_sha256", "destination_result_sha256", "deduplication_key_sha256"})


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _canonical(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _stable_bytes(path: Path) -> bytes:
    absolute = Path(os.path.abspath(path))
    current = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        current /= part
        info = os.lstat(current)
        if stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)):
            raise ValueError(f"HANNA Sol admission manifest pinned path is reparsed: {current}")
    before = os.lstat(absolute)
    if not stat.S_ISREG(before.st_mode):
        raise ValueError(f"HANNA Sol admission manifest pinned dependency is not a regular file: {absolute}")
    descriptor = os.open(absolute, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        opened = os.fstat(descriptor)
        identity = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
        if identity != (opened.st_dev, opened.st_ino, opened.st_size, opened.st_mtime_ns):
            raise ValueError("HANNA Sol admission manifest pinned dependency changed during open")
        chunks: list[bytes] = []
        while chunk := os.read(descriptor, 1024 * 1024):
            chunks.append(chunk)
        after_open, after_path = os.fstat(descriptor), os.lstat(absolute)
        if (opened.st_dev, opened.st_ino, opened.st_size, opened.st_mtime_ns, opened.st_ctime_ns) != (after_open.st_dev, after_open.st_ino, after_open.st_size, after_open.st_mtime_ns, after_open.st_ctime_ns) or identity != (after_path.st_dev, after_path.st_ino, after_path.st_size, after_path.st_mtime_ns):
            raise ValueError("HANNA Sol admission manifest pinned dependency changed during read")
        return b"".join(chunks)
    finally:
        os.close(descriptor)


def _read_canonical(admission: ModuleType, path: Path, label: str) -> dict[str, Any]:
    raw = admission._stable_bytes(path)
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"HANNA Sol admission manifest {label} is invalid") from error
    if not isinstance(value, dict) or _canonical(value) != raw:
        raise ValueError(f"HANNA Sol admission manifest {label} is not canonical")
    return value


def _load_admission() -> ModuleType:
    raw = _stable_bytes(ADMISSION_PATH)
    if _sha(raw) != ADMISSION_SHA256 or _sha(_stable_bytes(ADMISSION_CONTRACT_PATH)) != ADMISSION_CONTRACT_SHA256:
        raise ValueError("HANNA Sol admission manifest pinned admission verifier drifted")
    module = ModuleType("_hanna_sol_admission_manifest_admission")
    module.__file__ = str(ADMISSION_PATH)
    exec(compile(raw, str(ADMISSION_PATH), "exec"), module.__dict__)
    if _sha(_stable_bytes(ADMISSION_PATH)) != ADMISSION_SHA256 or module.contract().get("study_id") != "hbq-human-alignment-optimizer-v4-sol-local-lifecycle-admission-v1":
        raise ValueError("HANNA Sol admission manifest admission verifier changed during load")
    return module


def contract(admission: ModuleType) -> dict[str, Any]:
    value = _read_canonical(admission, CONTRACT_PATH, "contract")
    expected = {
        "format_version": 1, "study_id": STUDY_ID,
        "kind": "provider_free_public_manifest_of_sol_local_lifecycle_admissions",
        "inputs": {"admission_sha256": ADMISSION_SHA256, "admission_contract_sha256": ADMISSION_CONTRACT_SHA256, "frozen_successor_sha256": FROZEN_SUCCESSOR_SHA256, "hanna_csv_sha256": HANNA_CSV_SHA256},
        "geometry": {"original_sol_schedule_cells": 35, "excluded_original_terminal_cells": sorted(TERMINAL_CELLS), "admitted_original_sol_cells": EXPECTED_PROOF_COUNT},
        "ceiling": {"provider_calls_made": 0, "provider_attested": False, "native_endpoint_contact_cardinality": "unproven", "native_contact_proven": False, "evidence_status": "local_lifecycle_verified_native_endpoint_contact_cardinality_unproven"},
        "public_result": "canonical_ids_hashes_and_ceilings_only_no_absolute_paths_or_story_text",
        "claims": {"provider_contact": False, "selection": False, "generalization": False, "endpoint_comparison": False},
    }
    if value != expected:
        raise ValueError("HANNA Sol admission manifest contract identity drifted")
    return value


def _expected_cells(admission: ModuleType, frozen_successor_path: Path, hanna_csv_path: Path) -> frozenset[str]:
    if _sha(admission._stable_bytes(frozen_successor_path)) != FROZEN_SUCCESSOR_SHA256 or _sha(admission._stable_bytes(hanna_csv_path)) != HANNA_CSV_SHA256:
        raise ValueError("HANNA Sol admission manifest frozen inputs drifted")
    execution = admission._load_execution()
    schedule = execution._load_predecessor().derive_schedule(frozen_successor_path=Path(frozen_successor_path), hanna_csv_path=Path(hanna_csv_path))
    sol_cells = {row["cell_id"] for row in schedule["mandatory_development"] if row.get("route_name") == "sol_validation"}
    if len(sol_cells) != 35 or not TERMINAL_CELLS < sol_cells:
        raise ValueError("HANNA Sol admission manifest original Sol geometry drifted")
    expected = frozenset(sol_cells - TERMINAL_CELLS)
    if len(expected) != EXPECTED_PROOF_COUNT:
        raise ValueError("HANNA Sol admission manifest expected Sol admission count drifted")
    return expected


def _proof_paths(admission: ModuleType, proof_root: Path) -> list[Path]:
    root = Path(proof_root)
    admission._plain_ancestry(root, include_leaf=True)
    if not root.is_dir():
        raise ValueError("HANNA Sol admission manifest proof root is not a directory")
    entries = sorted(root.iterdir(), key=lambda entry: entry.name)
    if len(entries) != EXPECTED_PROOF_COUNT or any(not entry.is_file() or entry.suffix != ".json" for entry in entries):
        raise ValueError("HANNA Sol admission manifest requires exactly 33 direct canonical proof files")
    return entries


def _public_cell(proof: Mapping[str, Any], raw_proof: bytes) -> dict[str, str]:
    key = proof.get("deduplication_key")
    if not isinstance(key, dict):
        raise ValueError("HANNA Sol admission manifest proof deduplication identity is invalid")
    result = {"cell_id": proof.get("cell_id"), "proof_sha256": _sha(raw_proof), "source_receipt_sha256": proof.get("source_receipt_sha256"), "destination_result_sha256": proof.get("destination_result_sha256"), "deduplication_key_sha256": _sha(_canonical(key))}
    if set(result) != CELL_FIELDS or any(not isinstance(value, str) or not value for value in result.values()):
        raise ValueError("HANNA Sol admission manifest public cell projection is invalid")
    return result


def build_manifest(*, proof_root: Path, frozen_successor_path: Path, hanna_csv_path: Path) -> dict[str, Any]:
    """Authenticate all original successful lifecycle proofs before public projection."""
    admission = _load_admission()
    contract(admission)
    expected_cells = _expected_cells(admission, Path(frozen_successor_path), Path(hanna_csv_path))
    proofs: list[tuple[dict[str, Any], bytes]] = []
    for path in _proof_paths(admission, Path(proof_root)):
        raw = admission._stable_bytes(path)
        proof = admission._validate_prior_proof(path, execution=admission._load_execution(), frozen_successor_path=Path(frozen_successor_path), hanna_csv_path=Path(hanna_csv_path))
        if _canonical(proof) != raw:
            raise ValueError("HANNA Sol admission manifest proof changed during authentication")
        proofs.append((proof, raw))
    cells = [_public_cell(proof, raw) for proof, raw in proofs]
    cell_ids = [cell["cell_id"] for cell in cells]
    if set(cell_ids) != expected_cells or len(cell_ids) != len(set(cell_ids)):
        raise ValueError("HANNA Sol admission manifest proofs are partial, swapped, terminal, or duplicated")
    keys = [proof["deduplication_key"] for proof, _raw in proofs]
    if len({_canonical(key) for key in keys}) != EXPECTED_PROOF_COUNT:
        raise ValueError("HANNA Sol admission manifest complete deduplication key is reused")
    for identity in ("contact_id", "session_id"):
        values = [key.get(identity) for key in keys]
        if any(not isinstance(value, str) or not value for value in values) or len(values) != len(set(values)):
            raise ValueError(f"HANNA Sol admission manifest {identity} is reused")
    cells.sort(key=lambda cell: cell["cell_id"])
    return {"format_version": 1, "study_id": STUDY_ID, "kind": "sol_local_lifecycle_admission_public_manifest",
            "inputs": {"admission_sha256": ADMISSION_SHA256, "admission_contract_sha256": ADMISSION_CONTRACT_SHA256, "frozen_successor_sha256": FROZEN_SUCCESSOR_SHA256, "hanna_csv_sha256": HANNA_CSV_SHA256},
            "counts": {"admitted_original_sol_cells": EXPECTED_PROOF_COUNT, "provider_calls_made": 0},
            "ceiling": {"provider_attested": False, "native_contact_proven": False, "native_endpoint_contact_cardinality": "unproven", "evidence_status": "local_lifecycle_verified_native_endpoint_contact_cardinality_unproven"},
            "cells": cells}


def write_manifest(*, proof_root: Path, frozen_successor_path: Path, hanna_csv_path: Path, result_path: Path) -> dict[str, Any]:
    manifest = build_manifest(proof_root=proof_root, frozen_successor_path=frozen_successor_path, hanna_csv_path=hanna_csv_path)
    admission = _load_admission()
    output = Path(result_path)
    if output.exists():
        raise ValueError("HANNA Sol admission manifest refuses result overwrite")
    admission._new_file(output, _canonical(manifest))
    if _read_canonical(admission, output, "result") != manifest or set(manifest) != RESULT_FIELDS:
        raise ValueError("HANNA Sol admission manifest result publication drifted")
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--proof-root", required=True, type=Path)
    parser.add_argument("--frozen-successor-path", required=True, type=Path)
    parser.add_argument("--hanna-csv-path", required=True, type=Path)
    parser.add_argument("--result-path", required=True, type=Path)
    args = parser.parse_args(argv)
    print(_canonical(write_manifest(**vars(args))).decode("utf-8"), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
