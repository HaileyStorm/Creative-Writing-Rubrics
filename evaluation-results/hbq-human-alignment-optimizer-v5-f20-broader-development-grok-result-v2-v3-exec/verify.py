"""Verify the public broader Grok result or replay its immutable V3 receipts."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import os
import re
import stat
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path
from types import ModuleType
from typing import Any


HERE = Path(__file__).resolve().parent
STUDY_ID = "hbq-human-alignment-optimizer-v5-f20-broader-development-grok-result-v2-v3-exec"
V1_ID = "hbq-human-alignment-optimizer-v5-f20-broader-development-grok-result-v1"
V1_COMMIT = "29a0f59d7ed66270ce212c1247a82a0db0d1504d"
V1_FILES = {
    f"evaluation-results/{V1_ID}/README.md": "52804951f6ede439b939b046cc2d938c56b639ee4c502f4dda6adbd5ee20fc6c",
    f"evaluation-results/{V1_ID}/study-contract.json": "546099fed9ea0808ec9790b57565117770ebf3f1f29f51ef2908926c4cc5fec8",
    f"evaluation-results/{V1_ID}/verify.py": "12eb81d5195b968d8a33a633ec6c86fa0beb822239aea1d4d912b5fede311b96",
    "tests/test_hbq_human_alignment_optimizer_v5_f20_broader_development_grok_result_v1.py": "50edf8a0688da9266f64b8f01a7ecd672fdb6f2a0c24f634487128c5ce44a186",
}
V3_ID = "hbq-human-alignment-optimizer-v5-f20-broader-development-grok-exec-v3-threadsafe-route-load"
V3_COMMIT = "ab8613ef4238ff4c8cac7ef961d9b300053b42bc"
V3_FILES = {
    f"evaluation-results/{V3_ID}/executor.py": "24d38e0de28d20bcb1f87bb4af5737d4dc2a588bdf79e04e7c1a52f5de3ec3da",
    f"evaluation-results/{V3_ID}/study-contract.json": "d85610ccf354dc8d5aa639cbc0a5ece89bcf0720495445cd252c651dd59590c5",
    f"evaluation-results/{V3_ID}/README.md": "49846137b273758c20bb57109dfbb09dc76aa2c2fd7442f471f85430a583a7a6",
    "tests/test_hbq_human_alignment_optimizer_v5_f20_broader_development_grok_exec_v3_threadsafe_route_load.py": "05ad67fb73422421528eb704b3ad6f398b05fd4db73bfa87292b4674ded832e6",
}
COLLECTOR_SHA256 = "09a76419e4be6be186b580b985487f764c50ec3a164125bf934e717ea8ffb18b"
PUBLIC_FILES = {"README.md", "result.json", "study-contract.json", "verify.py"}
README_SHA256 = "f0f814d4389c1ef3b19ae80667e433682c80faf0c13d82305c2cc3e948fefeca"
RESULT_SHA256 = "89d18aa68e8285dd9cbe8f996413672aec3c19b740c869b2bbca66c54ccd3a32"
AUTHORITY = {"selection": "grok_development_only", "confirmation": "unopened", "generalization": "none", "promotion": "none", "runtime": "none", "endpoint_pooling": "forbidden"}
CLAIM = "DESCRIPTIVE_GROK_DEVELOPMENT_ONLY; no Sol, generalization, confirmation, promotion, runtime, or endpoint-pooled claim"
EVIDENCE_CEILING = {"native_endpoint_contact_cardinality": "unproven", "process_lifecycle_receipts": 35, "provider_calls_made": None}
RESULT_KIND = "descriptive_broader_grok_development_equal_group_mae_v3_execution"
CONTRACT_KIND = "public_broader_grok_development_result"
SOURCE_EXECUTION = {"collector_sha256": COLLECTOR_SHA256, "freeze_commit": "436da1ef3f8cf239203ac6a80afe8f72708c0415", "freeze_schedule_sha256": "bdb40b0f24f07ea938d57951768101a93ff62575919075abcd7bb9534e12c52c", "result_analyzer_v1_commit": V1_COMMIT, "result_analyzer_v1_verify_sha256": V1_FILES[f"evaluation-results/{V1_ID}/verify.py"], "v3_commit": V3_COMMIT, "v3_executor_sha256": V3_FILES[f"evaluation-results/{V3_ID}/executor.py"], "v3_study_contract_sha256": V3_FILES[f"evaluation-results/{V3_ID}/study-contract.json"]}
PATH_PATTERN = re.compile(r"(?:[A-Za-z]:[\\/]|\\\\[^\\]+\\[^\\]+|/(?:Users|home|private|tmp)/)")
SENSITIVE_KEYS = {"local_path", "native_request", "native_response", "payload", "prompt", "raw_output", "request_id", "session_id", "story_text", "writing"}


def canonical(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")


def sha256(value: bytes | Any) -> str:
    return hashlib.sha256(value if isinstance(value, bytes) else canonical(value)).hexdigest()


def _plain(path: Path, *, directory: bool | None = None) -> None:
    info = os.lstat(path)
    if stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)):
        raise ValueError("unsafe or reparsed path")
    if directory is not None and stat.S_ISDIR(info.st_mode) != directory:
        raise ValueError("unexpected path type")


def _safe(path: Path, *, directory: bool | None = None) -> Path:
    absolute = Path(os.path.abspath(path)); current = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        current /= part
        if not current.exists():
            raise ValueError("required path is absent")
        _plain(current, directory=current != absolute or directory)
    return absolute


def stable(path: Path) -> bytes:
    path = _safe(path, directory=False); before = os.lstat(path)
    with path.open("rb") as handle:
        opened = os.fstat(handle.fileno()); raw = handle.read(); after = os.fstat(handle.fileno())
    if (before.st_dev, before.st_ino, before.st_size) != (opened.st_dev, opened.st_ino, opened.st_size) or (opened.st_dev, opened.st_ino, opened.st_size) != (after.st_dev, after.st_ino, after.st_size):
        raise ValueError("stable read drift")
    return raw


def strict(raw: bytes, label: str) -> dict[str, Any]:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        value: dict[str, Any] = {}
        for key, child in items:
            if key in value:
                raise ValueError(f"duplicate key in {label}")
            value[key] = child
        return value
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=pairs, parse_constant=lambda token: (_ for _ in ()).throw(ValueError(token)))
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise ValueError(f"invalid {label}") from error
    if type(value) is not dict:
        raise ValueError(f"{label} must be an object")
    return value


def _canonical(path: Path, label: str) -> tuple[bytes, dict[str, Any]]:
    raw = stable(path); value = strict(raw, label)
    if raw != canonical(value):
        raise ValueError(f"{label} is not canonical")
    return raw, value


def _reject_sensitive(value: Any) -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            if not isinstance(key, str) or key.lower() in SENSITIVE_KEYS:
                raise ValueError("public surface contains sensitive material")
            _reject_sensitive(child)
    elif isinstance(value, list):
        for child in value:
            _reject_sensitive(child)
    elif isinstance(value, str) and PATH_PATTERN.search(value):
        raise ValueError("public surface contains a local path")


def _blob(repo: Path, commit: str, relative: str) -> bytes:
    result = subprocess.run(["git", "-C", str(repo), "show", f"{commit}:{relative}"], capture_output=True, check=False)
    if result.returncode:
        raise ValueError("pinned Git source is absent")
    return result.stdout


def _load_v1(repo: Path) -> ModuleType:
    for relative, digest in V1_FILES.items():
        raw = stable(repo / relative)
        if sha256(raw) != digest or _blob(repo, V1_COMMIT, relative) != raw:
            raise ValueError("pinned result-analyzer V1 drifted")
    path = repo / f"evaluation-results/{V1_ID}/verify.py"; raw = stable(path)
    spec = importlib.util.spec_from_file_location("_broader_grok_result_v1", path)
    if spec is None or spec.loader is None:
        raise ValueError("cannot load result-analyzer V1")
    module = importlib.util.module_from_spec(spec); sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(spec.name, None)
    if stable(path) != raw:
        raise ValueError("result-analyzer V1 changed during load")
    return module


def _verify_v3(repo: Path) -> None:
    for relative, digest in V3_FILES.items():
        raw = stable(repo / relative)
        if sha256(raw) != digest or _blob(repo, V3_COMMIT, relative) != raw:
            raise ValueError("pinned V3 execution dependency drifted")


def _render(replayed: Mapping[str, Any]) -> dict[str, Any]:
    if replayed.get("authority") != AUTHORITY or replayed.get("claim") != CLAIM or replayed.get("evidence_ceiling") != EVIDENCE_CEILING:
        raise ValueError("V3 replay semantic commitments drifted")
    source = replayed.get("source_execution")
    if not isinstance(source, Mapping) or source.get("freeze_commit") != SOURCE_EXECUTION["freeze_commit"] or source.get("freeze_schedule_sha256") != SOURCE_EXECUTION["freeze_schedule_sha256"]:
        raise ValueError("V3 replay source commitments drifted")
    value = {"authority": AUTHORITY, "claim": CLAIM, "evidence_ceiling": EVIDENCE_CEILING, "format_version": 1, "kind": RESULT_KIND, "metrics": replayed["metrics"], "parent_vs_descendant": replayed["parent_vs_descendant"], "selection": replayed["selection"], "source_execution": SOURCE_EXECUTION, "study_id": STUDY_ID}
    value["result_internal_sha256"] = sha256(value)
    return value


def replay(*, frozen_root: Path, normalized_root: Path, materialization_root: Path, frozen_successor_path: Path, hanna_csv_path: Path, output_root: Path, collector_path: Path) -> dict[str, Any]:
    repo = HERE.parents[1]; _verify_v3(repo)
    if sha256(stable(Path(collector_path))) != COLLECTOR_SHA256:
        raise ValueError("pinned V3 collector drifted")
    base = _load_v1(repo)
    base.V2_ID, base.V2_RELATIVE = V3_ID, f"evaluation-results/{V3_ID}"
    replayed = base.replay(frozen_root=Path(frozen_root), normalized_root=Path(normalized_root), materialization_root=Path(materialization_root), frozen_successor_path=Path(frozen_successor_path), hanna_csv_path=Path(hanna_csv_path), output_root=Path(output_root), collector_path=Path(collector_path), v2_commit=V3_COMMIT, v2_executor_sha256=V3_FILES[f"evaluation-results/{V3_ID}/executor.py"], v2_contract_sha256=V3_FILES[f"evaluation-results/{V3_ID}/study-contract.json"])
    return _render(replayed)


def _derived(result: Mapping[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    rows = result.get("metrics")
    if not isinstance(rows, list) or len(rows) != 5:
        raise ValueError("published metric geometry drifted")
    expected_groups: set[str] | None = None
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, Mapping) or set(row) != {"candidate_id", "cells", "equal_group_mae", "group_mae"} or not isinstance(row.get("candidate_id"), str) or row["candidate_id"] in seen or row.get("cells") != 7 or not isinstance(row.get("group_mae"), Mapping) or len(row["group_mae"]) != 7:
            raise ValueError("published metric fields drifted")
        group_ids = set(row["group_mae"])
        if expected_groups is None:
            expected_groups = group_ids
        if group_ids != expected_groups:
            raise ValueError("published group geometry drifted")
        values = [row["equal_group_mae"], *row["group_mae"].values()]
        if any(isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) for value in values) or row["equal_group_mae"] != sum(row["group_mae"].values()) / 7:
            raise ValueError("published MAE drifted")
        seen.add(row["candidate_id"])
    ordered = sorted(rows, key=lambda row: (row["equal_group_mae"], row["candidate_id"]))
    if rows != ordered:
        raise ValueError("published metric ordering drifted")
    parent = next((row for row in rows if row["candidate_id"] == "normalized-nextwave-08-conservative-hybrid"), None)
    if parent is None or parent["equal_group_mae"] <= 0:
        raise ValueError("published parent identity drifted")
    selection = {"candidate_id": rows[0]["candidate_id"], "equal_group_mae": rows[0]["equal_group_mae"], "tie_breakers": ["equal_group_mae:ascending", "candidate_id:lexicographic"]}
    descendants = [{"candidate_id": row["candidate_id"], "absolute_delta": row["equal_group_mae"] - parent["equal_group_mae"], "relative_reduction": -(row["equal_group_mae"] - parent["equal_group_mae"]) / parent["equal_group_mae"]} for row in rows if row["candidate_id"] != parent["candidate_id"]]
    return selection, descendants


def validate_publication() -> dict[str, Any]:
    root = _safe(HERE, directory=True)
    if {path.name for path in root.iterdir()} != PUBLIC_FILES:
        raise ValueError("public package inventory drifted")
    for name in PUBLIC_FILES:
        _plain(root / name, directory=False)
    readme_raw = stable(root / "README.md"); readme = readme_raw.decode("utf-8")
    contract_raw, contract = _canonical(root / "study-contract.json", "study contract")
    result_raw, result = _canonical(root / "result.json", "public result")
    _reject_sensitive(readme); _reject_sensitive(contract); _reject_sensitive(result)
    expected_contract = {"authority", "contract_internal_sha256", "evidence_ceiling", "format_version", "kind", "publication_manifest", "result_internal_sha256", "source_execution", "study_id"}
    if set(contract) != expected_contract or contract.get("study_id") != STUDY_ID or contract.get("format_version") != 1 or contract.get("kind") != CONTRACT_KIND:
        raise ValueError("public contract identity drifted")
    internal_contract = dict(contract); internal_contract.pop("contract_internal_sha256")
    if contract.get("contract_internal_sha256") != sha256(internal_contract):
        raise ValueError("public contract commitment drifted")
    manifest = contract.get("publication_manifest")
    if not isinstance(manifest, Mapping) or set(manifest) != {"inventory", "bound_files"} or manifest.get("inventory") != sorted(PUBLIC_FILES) or set(manifest.get("bound_files", {})) != {"README.md", "result.json", "verify.py"}:
        raise ValueError("publication manifest drifted")
    for name, digest in manifest["bound_files"].items():
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest) or sha256(stable(root / name)) != digest:
            raise ValueError("bound public file drifted")
    expected_result = {"authority", "claim", "evidence_ceiling", "format_version", "kind", "metrics", "parent_vs_descendant", "result_internal_sha256", "selection", "source_execution", "study_id"}
    if set(result) != expected_result or result.get("study_id") != STUDY_ID or result.get("format_version") != 1 or result.get("kind") != RESULT_KIND:
        raise ValueError("public result identity drifted")
    internal_result = dict(result); internal_result.pop("result_internal_sha256")
    if result.get("result_internal_sha256") != sha256(internal_result) or contract.get("result_internal_sha256") != result["result_internal_sha256"] or contract.get("authority") != result["authority"] or contract.get("evidence_ceiling") != result["evidence_ceiling"] or contract.get("source_execution") != result["source_execution"]:
        raise ValueError("public result/contract binding drifted")
    if sha256(readme_raw) != README_SHA256 or sha256(result_raw) != RESULT_SHA256 or result.get("authority") != AUTHORITY or result.get("claim") != CLAIM or result.get("evidence_ceiling") != EVIDENCE_CEILING or contract.get("authority") != AUTHORITY or contract.get("evidence_ceiling") != EVIDENCE_CEILING or result.get("source_execution") != SOURCE_EXECUTION or contract.get("source_execution") != SOURCE_EXECUTION:
        raise ValueError("immutable public semantic commitment drifted")
    selection, descendants = _derived(result)
    if result.get("selection") != selection or result.get("parent_vs_descendant") != descendants:
        raise ValueError("published selection or descendant deltas drifted")
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("frozen-root", "normalized-root", "materialization-root", "frozen-successor", "hanna-csv", "output-root", "collector-path"):
        parser.add_argument("--" + name)
    args = parser.parse_args(argv)
    names = ("frozen_root", "normalized_root", "materialization_root", "frozen_successor", "hanna_csv", "output_root", "collector_path")
    values = [getattr(args, name) for name in names]
    published = validate_publication()
    if any(values) and not all(values):
        parser.error("provide every replay input or none")
    if all(values):
        replayed = replay(frozen_root=Path(args.frozen_root), normalized_root=Path(args.normalized_root), materialization_root=Path(args.materialization_root), frozen_successor_path=Path(args.frozen_successor), hanna_csv_path=Path(args.hanna_csv), output_root=Path(args.output_root), collector_path=Path(args.collector_path))
        if replayed != published:
            raise ValueError("independent V3 replay differs from public result")
        print(canonical({"cells": 35, "provider_calls_made": 0, "replay": "verified"}).decode("utf-8"), end="")
    else:
        print(canonical({"binding_scope": sorted(PUBLIC_FILES), "provider_calls_made": 0, "publication": "verified"}).decode("utf-8"), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
