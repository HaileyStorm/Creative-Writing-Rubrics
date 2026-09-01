"""Independently replay a lower-step Grok development collector without contact."""
from __future__ import annotations

import argparse
import base64
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
STUDY_ID = "hbq-human-alignment-optimizer-v6-desc13-lower-step-grok-result-v1"
EXECUTOR_ID = "hbq-human-alignment-optimizer-v6-desc13-lower-step-grok-exec-v1"
EXECUTOR_COMMIT = "6411361bc2929f95cc7d745ddd90a5162e2226c5"
CANDIDATE_ID = "hbq-human-alignment-optimizer-v6-desc13-lower-step-candidates-v1"
CANDIDATE_COMMIT = "02bdbf5c1adc4fa44a0b39b46e5bb9895f4d95d4"
FREEZE_ID = "hbq-human-alignment-optimizer-v5-f20-broader-development-freeze-v1"
FREEZE_COMMIT = "436da1ef3f8cf239203ac6a80afe8f72708c0415"
SCHEDULE_KIND = "frozen_descendant13_lower_step_grok_development_schedule"
COLLECTOR_KIND = "complete_35_broader_grok_receipts_cardinality_unproven"
PARENT = "broader-nextwave-13-missing_evidence_not_no"
DIMENSIONS = ("Relevance", "Coherence", "Empathy", "Surprise", "Engagement", "Complexity")
PUBLIC_FILES = {"README.md", "study-contract.json", "verify.py"}
AUTHORITY = {"confirmation": "unopened", "dspy_optuna_runtime": "forbidden", "endpoint_pooling": "forbidden", "generalization": "none", "promotion": "none", "runtime": "none", "selection": "grok_development_only"}
CANDIDATE_FILES = {
    f"evaluation-results/{CANDIDATE_ID}/study.py": "511066c8b8723b1df04a07eae4eb0daa7fb375169ba2a23c442fc848b2ef8dae",
    f"evaluation-results/{CANDIDATE_ID}/study-contract.json": "74aa271918c4e9d15cd48f797f4b94814f7cf41344ace7a2c65a56a9fa06acfa",
    f"evaluation-results/{CANDIDATE_ID}/README.md": "a62ffb01d9ac453470a886270251689d6d472080b4cce58090227e8add95bc67",
}
EXECUTOR_FILES = {
    f"evaluation-results/{EXECUTOR_ID}/executor.py": "ad86eb68ccd2bad67473e3f54f6191fb8654b2bfd33a937efbbcda94e3a49ec6",
    f"evaluation-results/{EXECUTOR_ID}/study-contract.json": "66017a72f570d388d5f5cb84ac66b9cfd05bb42e711ac0d1770b6156c2fbcddd",
    f"evaluation-results/{EXECUTOR_ID}/README.md": "ea0378ae7a25cf5dd78ecbec4e8cf837fb10d4b52a29ce8a20cd84f81354abc5",
}
FREEZE_FILES = {
    f"evaluation-results/{FREEZE_ID}/study.py": "507e3c0bec1af6d0acef6e806cf6874a2633e892c9bbf567728f436af30f84bf",
    f"evaluation-results/{FREEZE_ID}/study-contract.json": "3b31c9b0d5ec4c71d6b562045dcd52b2646380cb318d72b83d2119e760543a77",
    f"evaluation-results/{FREEZE_ID}/README.md": "5f8956e96df28ddfe37533e631c163f1cdbf711e820e05e2607618975bf0e75f",
}
PATH_PATTERN = re.compile(r"(?:[A-Za-z]:[\\\\/]|\\\\\\\\[^\\]+\\[^\\]+|/(?:Users|home|private|tmp)/)")


def canonical(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")


def sha256(value: bytes | Any) -> str:
    return hashlib.sha256(value if isinstance(value, bytes) else canonical(value)).hexdigest()


def _ancestry(path: Path, *, directory: bool) -> tuple[tuple[str, int, int, int, int, int | None], ...]:
    target = Path(os.path.abspath(path)); values: list[tuple[str, int, int, int, int, int | None]] = []
    for index, current in enumerate((target, *target.parents)):
        try:
            info = os.lstat(current)
        except OSError as error:
            raise ValueError("artifact ancestry cannot be inspected") from error
        if stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)):
            raise ValueError("unsafe or reparsed path")
        expected_directory = directory if index == 0 else True
        if stat.S_ISDIR(info.st_mode) != expected_directory:
            raise ValueError("unexpected path type")
        values.append((str(current), info.st_dev, info.st_ino, stat.S_IFMT(info.st_mode), info.st_mtime_ns, None if expected_directory else info.st_size))
    return tuple(values)


def _plain(path: Path, *, directory: bool | None = None) -> None:
    _ancestry(path, directory=False if directory is None else directory)


def _safe(path: Path, *, directory: bool | None = None) -> Path:
    absolute = Path(os.path.abspath(path)); current = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        current /= part
        if not current.exists():
            raise ValueError("required path is absent")
        _plain(current, directory=current != absolute or directory)
    return absolute


def stable(path: Path) -> bytes:
    raw, _identity = _stable_read(path)
    return raw


def _stable_read(path: Path) -> tuple[bytes, tuple[tuple[str, int, int, int, int, int | None], ...]]:
    path = _safe(path, directory=False); before = _ancestry(path, directory=False)
    with path.open("rb") as handle:
        opened = os.fstat(handle.fileno()); raw = handle.read(); after = os.fstat(handle.fileno())
    final = _ancestry(path, directory=False)
    identity = (opened.st_dev, opened.st_ino, stat.S_IFMT(opened.st_mode), opened.st_size)
    if before != final or before[0][1:4] != identity[:3] or before[0][-1] != identity[-1] or identity != (after.st_dev, after.st_ino, stat.S_IFMT(after.st_mode), after.st_size):
        raise ValueError("stable full-ancestry read drift")
    return raw, before


def strict(raw: bytes, label: str) -> dict[str, Any]:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            if key in result:
                raise ValueError(f"duplicate key in {label}")
            result[key] = value
        return result
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=pairs, parse_constant=lambda token: (_ for _ in ()).throw(ValueError(token)))
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise ValueError(f"invalid {label}") from error
    if type(value) is not dict or raw != canonical(value):
        raise ValueError(f"noncanonical {label}")
    return value


def _canonical(path: Path, label: str) -> tuple[bytes, dict[str, Any]]:
    raw = stable(path)
    return raw, strict(raw, label)


def _blob(repo: Path, commit: str, relative: str) -> bytes:
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ValueError("source commit must be a full SHA-1")
    result = subprocess.run(["git", "-C", str(repo), "show", f"{commit}:{relative}"], capture_output=True, check=False)
    if result.returncode:
        raise ValueError("pinned Git source is absent")
    return result.stdout


def _load(path: Path, name: str) -> ModuleType:
    raw = stable(path); spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ValueError("cannot load pinned module")
    module = importlib.util.module_from_spec(spec); sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(name, None)
    if stable(path) != raw:
        raise ValueError("pinned module changed during load")
    return module


def _verify_files(repo: Path, files: Mapping[str, str], *, commit: str | None) -> None:
    for relative, digest in files.items():
        raw = stable(repo / relative)
        if sha256(raw) != digest or (commit is not None and _blob(repo, commit, relative) != raw):
            raise ValueError("pinned dependency drifted or is not committed")


def _load_freeze(repo: Path) -> ModuleType:
    _verify_files(repo, FREEZE_FILES, commit=FREEZE_COMMIT)
    return _load(repo / f"evaluation-results/{FREEZE_ID}/study.py", "_desc13_lower_result_freeze")


def _load_executor(repo: Path) -> ModuleType:
    if not re.fullmatch(r"[0-9a-f]{40}", EXECUTOR_COMMIT):
        raise ValueError("executor checkpoint is not committed; replay is fail-closed")
    _verify_files(repo, EXECUTOR_FILES, commit=EXECUTOR_COMMIT)
    value = _load(repo / f"evaluation-results/{EXECUTOR_ID}/executor.py", "_desc13_lower_result_executor")
    if value.STUDY_ID != EXECUTOR_ID:
        raise ValueError("execution identity drifted")
    return value


def _targets(freeze: ModuleType, *, frozen_root: Path, normalized_root: Path, materialization_root: Path, frozen_successor_path: Path, hanna_csv_path: Path) -> dict[str, dict[str, float]]:
    paths = {"frozen_root": (Path(frozen_root), True), "normalized_root": (Path(normalized_root), True), "materialization_root": (Path(materialization_root), True), "frozen_successor_path": (Path(frozen_successor_path), False), "hanna_csv_path": (Path(hanna_csv_path), False)}
    before = {name: _ancestry(path, directory=directory) for name, (path, directory) in paths.items()}
    persisted = freeze.validate_frozen_root(paths["frozen_root"][0])
    rebuilt = freeze.build(normalized_root=paths["normalized_root"][0], materialization_root=paths["materialization_root"][0], frozen_successor_path=paths["frozen_successor_path"][0], hanna_csv_path=paths["hanna_csv_path"][0])
    if canonical(persisted) != canonical(rebuilt):
        raise ValueError("development schedule does not independently reconstruct")
    groups = persisted.get("groups")
    development_items = {row.get("item_id") for row in groups if isinstance(row, Mapping)} if isinstance(groups, list) else set()
    if len(development_items) != 7 or not all(isinstance(item, str) and item for item in development_items):
        raise ValueError("seven development target identities drifted")
    study, _harness, _frozen, _split, _parents = freeze._v3()._material(frozen_successor_path=paths["frozen_successor_path"][0], hanna_csv_path=paths["hanna_csv_path"][0])
    targets = freeze._v3().v2_module()._human_targets(study=study, frozen_successor_path=paths["frozen_successor_path"][0], hanna_csv_path=paths["hanna_csv_path"][0])
    if not isinstance(targets, Mapping):
        raise TypeError("independent HANNA target reconstruction failed")
    after = {name: _ancestry(path, directory=directory) for name, (path, directory) in paths.items()}
    if before != after:
        raise ValueError("external HANNA input changed during independent reconstruction")
    selected = {item: targets[item] for item in development_items if item in targets}
    if set(selected) != development_items:
        raise ValueError("development target is absent from independent reconstruction")
    return selected


def _output_schedule(executor: ModuleType, *, output_root: Path, candidate_freeze_root: Path, development_freeze_root: Path) -> dict[str, Any]:
    rebuilt = executor.build_schedule(candidate_freeze_root=Path(candidate_freeze_root), development_freeze_root=Path(development_freeze_root))
    raw, persisted = _canonical(Path(output_root) / "schedule.json", "persisted lower-step schedule")
    if raw != canonical(rebuilt) or persisted.get("study_id") != EXECUTOR_ID or persisted.get("kind") != SCHEDULE_KIND:
        raise ValueError("persisted lower-step schedule differs from immutable inputs")
    return persisted


def _score(raw: bytes, extractor: Any) -> dict[str, float]:
    try:
        scores, coverage, reported = extractor(raw, provider="xai", model="grok-4.6")
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise ValueError("native response extraction drifted") from error
    if (not isinstance(scores, Mapping) or set(scores) != set(DIMENSIONS) or not isinstance(coverage, Mapping)
            or set(coverage) != set(DIMENSIONS) or not isinstance(reported, Mapping)):
        raise ValueError("native response extraction drifted")
    value = {key: scores[key] for key in DIMENSIONS}
    if any(isinstance(item, bool) or not isinstance(item, (int, float)) or not math.isfinite(item) for item in value.values()):
        raise ValueError("native scores are not finite numbers")
    return value


def _project(schedule: Mapping[str, Any], collector: Mapping[str, Any], targets: Mapping[str, Mapping[str, float]], extractor: Any) -> dict[str, Any]:
    cells, groups = schedule.get("cells"), schedule.get("groups")
    if (schedule.get("study_id") != EXECUTOR_ID or schedule.get("kind") != SCHEDULE_KIND
            or schedule.get("geometry") != {"candidates": 5, "development_groups": 7, "grok_cells": 35, "sol_cells": 0, "confirmation_cells": 0}
            or not isinstance(cells, list) or not isinstance(groups, list) or len(cells) != 35 or len(groups) != 7):
        raise ValueError("lower-step schedule geometry drifted")
    index = {row.get("cell_id"): row for row in cells if isinstance(row, Mapping)}
    candidate_ids = {row.get("candidate_id") for row in cells if isinstance(row, Mapping)}
    group_ids = {row.get("prompt_group_id") for row in groups if isinstance(row, Mapping)}
    group_items = {row.get("prompt_group_id"): row.get("item_id") for row in groups if isinstance(row, Mapping)}
    expected_collector = {"format_version", "study_id", "kind", "schedule_sha256", "authorization_acknowledgement_sha256", "route", "route_evidence", "cells", "native_endpoint_contact_cardinality", "provider_calls_made", "process_launches"}
    if (set(collector) != expected_collector or collector.get("format_version") != 1 or collector.get("study_id") != EXECUTOR_ID
            or collector.get("kind") != COLLECTOR_KIND or collector.get("schedule_sha256") != schedule.get("schedule_sha256")
            or collector.get("native_endpoint_contact_cardinality") != "unproven" or collector.get("provider_calls_made") != 0
            or collector.get("process_launches") != 0 or not isinstance(collector.get("route"), Mapping)
            or not isinstance(collector.get("route_evidence"), Mapping) or not re.fullmatch(r"[0-9a-f]{64}", str(collector.get("authorization_acknowledgement_sha256", "")))):
        raise ValueError("collector identity or caller aggregate surface drifted")
    supplied = collector.get("cells")
    cell_pairs = {(row.get("candidate_id"), row.get("prompt_group_id")) for row in cells if isinstance(row, Mapping)}
    if (not isinstance(supplied, list) or len(supplied) != 35 or len(index) != 35 or len(candidate_ids) != 5 or len(group_ids) != 7
            or len(group_items) != 7 or any(not isinstance(item, str) for item in group_items.values()) or len(cell_pairs) != 35
            or any(row.get("item_id") != group_items.get(row.get("prompt_group_id")) for row in cells if isinstance(row, Mapping))
            or PARENT not in candidate_ids):
        raise ValueError("collector or schedule geometry drifted")
    observed: dict[str, dict[str, float]] = {str(candidate): {} for candidate in candidate_ids}
    seen_cells: set[str] = set(); seen_contacts: set[tuple[str, str]] = set()
    required = {"cell_id", "payload_base64", "payload_sha256", "native_request_base64", "native_request_sha256", "native_response_base64", "native_response_sha256", "identity", "effective_settings", "effective_settings_sha256"}
    for entry in supplied:
        if not isinstance(entry, Mapping) or set(entry) != required:
            raise ValueError("collector cell fields drifted")
        cell_id = entry.get("cell_id"); row = index.get(cell_id)
        if not isinstance(cell_id, str) or cell_id in seen_cells or not isinstance(row, Mapping):
            raise ValueError("duplicate or unknown collector cell")
        try:
            request = base64.b64decode(entry["native_request_base64"], validate=True)
            response = base64.b64decode(entry["native_response_base64"], validate=True)
        except (TypeError, ValueError) as error:
            raise ValueError("collector native bytes are invalid") from error
        identity = entry.get("identity"); settings = entry.get("effective_settings")
        if not isinstance(identity, Mapping) or not isinstance(settings, Mapping):
            raise TypeError("native identity or settings are invalid")
        contact = (identity.get("request_id"), identity.get("session_id"))
        if (entry.get("payload_base64") != row.get("payload_base64") or entry.get("payload_sha256") != row.get("payload_sha256")
                or entry.get("native_request_sha256") != sha256(request) or entry.get("native_response_sha256") != sha256(response)
                or entry.get("effective_settings_sha256") != sha256(settings) or not all(isinstance(item, str) and item for item in contact)
                or contact in seen_contacts or identity.get("provider") != "xai" or identity.get("requested_model") != "grok-4.6"
                or identity.get("reported_model") != "grok-4.6-build" or identity.get("tools_enabled") is not False
                or settings.get("requested_model") != "grok-4.6" or settings.get("reported_model") != "grok-4.6-build"
                or settings.get("tools_enabled") is not False or settings.get("web_search_enabled") is not False or settings.get("subagents_enabled") is not False):
            raise ValueError("collector native request/response/settings/identity binding drifted")
        scores = _score(response, extractor); target = targets.get(row.get("item_id"))
        if not isinstance(target, Mapping) or set(target) != set(DIMENSIONS):
            raise ValueError("independent HANNA target binding drifted")
        observed[str(row["candidate_id"])][str(row["prompt_group_id"])] = sum(abs(scores[key] - target[key]) for key in DIMENSIONS) / len(DIMENSIONS)
        seen_cells.add(cell_id); seen_contacts.add(contact)
    if seen_cells != set(index):
        raise ValueError("partial collector cannot be mislabeled complete")
    metrics: list[dict[str, Any]] = []
    for candidate in sorted(candidate_ids):
        group_mae = observed[str(candidate)]
        if set(group_mae) != group_ids:
            raise ValueError("partial candidate cannot be imputed")
        ordered_group_mae = dict(sorted(group_mae.items()))
        equal_group_mae = sum(ordered_group_mae.values()) / len(ordered_group_mae)
        if equal_group_mae != sum(ordered_group_mae.values()) / 7:
            raise ValueError("one-cell-per-group endpoint parity drifted")
        metrics.append({"candidate_id": candidate, "cells": 7, "equal_group_mae": equal_group_mae, "group_mae": ordered_group_mae})
    metrics.sort(key=lambda row: (row["equal_group_mae"], row["candidate_id"]))
    parent = next(row for row in metrics if row["candidate_id"] == PARENT)
    if parent["equal_group_mae"] <= 0:
        raise ValueError("parent MAE must be positive")
    descendants = [{"candidate_id": row["candidate_id"], "absolute_delta": row["equal_group_mae"] - parent["equal_group_mae"], "relative_reduction": -(row["equal_group_mae"] - parent["equal_group_mae"]) / parent["equal_group_mae"]} for row in metrics if row["candidate_id"] != PARENT]
    return {"format_version": 1, "study_id": STUDY_ID, "kind": "descriptive_descendant13_lower_step_grok_development_equal_group_mae", "authority": {"selection": "grok_development_only", "confirmation": "unopened", "generalization": "none", "promotion": "none", "runtime": "none", "endpoint_pooling": "forbidden"}, "claim": "DESCRIPTIVE_GROK_DEVELOPMENT_ONLY; partial cells are not imputed and no Sol, generalization, confirmation, promotion, runtime, or endpoint-pooled claim follows", "evidence_ceiling": {"native_endpoint_contact_cardinality": "unproven", "process_lifecycle_receipts": 35, "provider_calls_made": None}, "metrics": metrics, "selection": {"candidate_id": metrics[0]["candidate_id"], "equal_group_mae": metrics[0]["equal_group_mae"], "tie_breakers": ["equal_group_mae:ascending", "candidate_id:lexicographic"]}, "parent_vs_descendant": descendants}


def _require_collector_binding(raw: bytes, ancestry: tuple[tuple[str, int, int, int, int, int | None], ...], replayed: Mapping[str, Any], collector_path: Path) -> None:
    if (replayed.get("cells") != 35 or replayed.get("equal_group_projection_ready") is not True
            or replayed.get("collector_sha256") != sha256(raw)
            or _ancestry(Path(collector_path), directory=False) != ancestry):
        raise ValueError("execution receipt replay is incomplete or collector changed")


def replay(*, candidate_freeze_root: Path, development_freeze_root: Path, normalized_root: Path, materialization_root: Path, frozen_successor_path: Path, hanna_csv_path: Path, output_root: Path, collector_path: Path) -> dict[str, Any]:
    repo = HERE.parents[1]; _verify_files(repo, CANDIDATE_FILES, commit=CANDIDATE_COMMIT)
    collector_raw, collector_ancestry = _stable_read(Path(collector_path)); collector = strict(collector_raw, "collector")
    executor = _load_executor(repo); schedule = _output_schedule(executor, output_root=Path(output_root), candidate_freeze_root=Path(candidate_freeze_root), development_freeze_root=Path(development_freeze_root))
    replayed = executor.replay_collector(output_root=Path(output_root), candidate_freeze_root=Path(candidate_freeze_root), development_freeze_root=Path(development_freeze_root), collector_path=Path(collector_path))
    _require_collector_binding(collector_raw, collector_ancestry, replayed, Path(collector_path))
    freeze = _load_freeze(repo); targets = _targets(freeze, frozen_root=Path(development_freeze_root), normalized_root=Path(normalized_root), materialization_root=Path(materialization_root), frozen_successor_path=Path(frozen_successor_path), hanna_csv_path=Path(hanna_csv_path))
    result = _project(schedule, collector, targets, freeze._v3().v2_module()._extract_native)
    result["source_execution"] = {"candidate_commit": CANDIDATE_COMMIT, "candidate_manifest_sha256": schedule["candidate_freeze_manifest_sha256"], "development_schedule_sha256": schedule["development_schedule_sha256"], "executor_commit": EXECUTOR_COMMIT, "executor_sha256": EXECUTOR_FILES[f"evaluation-results/{EXECUTOR_ID}/executor.py"], "executor_contract_sha256": EXECUTOR_FILES[f"evaluation-results/{EXECUTOR_ID}/study-contract.json"], "collector_sha256": sha256(collector_raw)}
    result["result_internal_sha256"] = sha256(result)
    return result


def _contract() -> dict[str, Any]:
    return {"authority": AUTHORITY, "format_version": 1, "kind": "provider_free_descendant13_lower_step_grok_result_analyzer", "pinned_candidate": {"commit": CANDIDATE_COMMIT, "manifest_sha256": "0487398345b28388fb6e35d879e5ea6f771f65802488e3fc33cf0426b530cecd", "readme_sha256": CANDIDATE_FILES[f"evaluation-results/{CANDIDATE_ID}/README.md"], "study_contract_sha256": CANDIDATE_FILES[f"evaluation-results/{CANDIDATE_ID}/study-contract.json"], "study_id": CANDIDATE_ID, "study_sha256": CANDIDATE_FILES[f"evaluation-results/{CANDIDATE_ID}/study.py"]}, "pinned_executor": {"commit": EXECUTOR_COMMIT, "executor_sha256": EXECUTOR_FILES[f"evaluation-results/{EXECUTOR_ID}/executor.py"], "readme_sha256": EXECUTOR_FILES[f"evaluation-results/{EXECUTOR_ID}/README.md"], "study_contract_sha256": EXECUTOR_FILES[f"evaluation-results/{EXECUTOR_ID}/study-contract.json"], "study_id": EXECUTOR_ID}, "study_id": STUDY_ID}


def _validate_contract(contract: Mapping[str, Any]) -> None:
    if dict(contract) != _contract():
        raise ValueError("prepared result package contract drifted")


def validate_package() -> dict[str, Any]:
    root = _safe(HERE, directory=True)
    if {path.name for path in root.iterdir() if path.name != "__pycache__"} != PUBLIC_FILES:
        raise ValueError("prepared result package inventory drifted")
    _raw, contract = _canonical(root / "study-contract.json", "study contract")
    readme = stable(root / "README.md").decode("utf-8")
    if PATH_PATTERN.search(readme) or PATH_PATTERN.search(canonical(contract).decode("utf-8")):
        raise ValueError("prepared public surface contains a local path")
    _validate_contract(contract)
    return contract


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("candidate-freeze-root", "development-freeze-root", "normalized-root", "materialization-root", "frozen-successor", "hanna-csv", "output-root", "collector-path"):
        parser.add_argument("--" + name)
    args = parser.parse_args(argv)
    names = ("candidate_freeze_root", "development_freeze_root", "normalized_root", "materialization_root", "frozen_successor", "hanna_csv", "output_root", "collector_path")
    values = [getattr(args, name) for name in names]; validate_package()
    if any(values) and not all(values):
        parser.error("provide every replay input or none")
    if not any(values):
        print(canonical({"prepared_package": "verified", "provider_calls_made": 0, "study_id": STUDY_ID}).decode("utf-8"), end=""); return 0
    result = replay(candidate_freeze_root=Path(args.candidate_freeze_root), development_freeze_root=Path(args.development_freeze_root), normalized_root=Path(args.normalized_root), materialization_root=Path(args.materialization_root), frozen_successor_path=Path(args.frozen_successor), hanna_csv_path=Path(args.hanna_csv), output_root=Path(args.output_root), collector_path=Path(args.collector_path))
    print(canonical(result).decode("utf-8"), end=""); return 0


if __name__ == "__main__":
    raise SystemExit(main())
