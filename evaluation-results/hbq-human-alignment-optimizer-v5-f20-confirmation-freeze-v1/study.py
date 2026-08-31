"""Provider-free immutable confirmation schedule after the broader development wave."""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import stat
import subprocess
from pathlib import Path
from typing import Any, Mapping


HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
STUDY_ID = "hbq-human-alignment-optimizer-v5-f20-confirmation-freeze-v1"
FREEZE_ID = "hbq-human-alignment-optimizer-v5-f20-broader-development-freeze-v1"
FREEZE_COMMIT = "436da1ef3f8cf239203ac6a80afe8f72708c0415"
FREEZE_SHA256 = "507e3c0bec1af6d0acef6e806cf6874a2633e892c9bbf567728f436af30f84bf"
V3_SHA256 = "8928b9af075486483f5d117daf34d10ed71b98407b897c8948181b66d1cb99c3"
FROZEN_SUCCESSOR_SHA256 = "b0f6dd24415c388a3104f8c9304ce301193cf0a48631a86c4886bc8ce48468e7"
HANNA_CSV_SHA256 = "ef59054d27fa32def06cfdc57243b1dd09c7e71f40b6d9d43fecfbf60e59026b"
MATERIALIZATION_SHA256 = "9a6db38703b0e34b96e856a956436e4bba76c9770f899943d75ecc436aca1a84"
GROK_RESULT_ID = "hbq-human-alignment-optimizer-v5-f20-broader-development-grok-result-v2-v3-exec"
GROK_RESULT_RELATIVE = f"evaluation-results/{GROK_RESULT_ID}/result.json"
GROK_RESULT_COMMIT = "5f50fbc2c345a55203cd2891d80037a797c6a1b4"
GROK_RESULT_SHA256 = "89d18aa68e8285dd9cbe8f996413672aec3c19b740c869b2bbca66c54ccd3a32"
SOL_RESULT_ID = "hbq-human-alignment-optimizer-v5-f20-broader-development-sol-result-v1"
SOL_RESULT_RELATIVE = f"evaluation-results/{SOL_RESULT_ID}/result.json"
SOL_RESULT_COMMIT = "91f12ffc12f8090bb174f2664602ec6e8e56076d"
SOL_RESULT_SHA256 = "34441a265fbf4d654b2de4e89acfcc4b436029f0ff8c7cca47c9759ffc922fa3"
BASELINE = "candidate-102cc7f06c9a99a7"
PARENT = "normalized-nextwave-08-conservative-hybrid"
SELECTED = "broader-nextwave-13-missing_evidence_not_no"
DIMENSIONS = ("Relevance", "Coherence", "Empathy", "Surprise", "Engagement", "Complexity")


def canonical(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")


def sha256(value: bytes | Any) -> str:
    return hashlib.sha256(value if isinstance(value, bytes) else canonical(value)).hexdigest()


def _pairs(pairs: list[tuple[str, Any]], label: str) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate key in {label}")
        result[key] = value
    return result


def _strict_raw(raw: bytes, label: str) -> dict[str, Any]:
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=lambda pairs: _pairs(pairs, label), parse_constant=lambda token: (_ for _ in ()).throw(ValueError(token)))
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise ValueError(f"{label} is not strict JSON") from error
    if not isinstance(value, dict) or canonical(value) != raw:
        raise ValueError(f"{label} must be canonical JSON")
    return value


def strict_json(path: Path, label: str) -> dict[str, Any]:
    return _strict_raw(_stable(Path(path)), label)


def _plain(path: Path, directory: bool) -> None:
    info = os.lstat(path)
    if stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)):
        raise ValueError("unsafe reparse artifact")
    if stat.S_ISDIR(info.st_mode) != directory:
        raise ValueError("unexpected artifact type")


def _stable(path: Path) -> bytes:
    _plain(path, directory=False)
    before = os.lstat(path)
    with path.open("rb") as handle:
        opened = os.fstat(handle.fileno())
        raw = handle.read()
        after = os.fstat(handle.fileno())
    identity = lambda value: (value.st_dev, value.st_ino, value.st_size)
    if identity(before) != identity(opened) or identity(opened) != identity(after):
        raise ValueError("stable read drift")
    return raw


def _git_blob(commit: str, relative: str) -> bytes:
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ValueError("result commit must be a full SHA-1")
    completed = subprocess.run(["git", "-C", str(REPO), "show", f"{commit}:{relative}"], capture_output=True, check=False)
    if completed.returncode:
        raise ValueError("required committed result blob is absent")
    return completed.stdout


def _load_freeze():
    path = HERE.parent / FREEZE_ID / "study.py"
    raw = _stable(path)
    if sha256(raw) != FREEZE_SHA256 or _git_blob(FREEZE_COMMIT, f"evaluation-results/{FREEZE_ID}/study.py") != raw:
        raise ValueError("pinned broader freeze drifted")
    namespace: dict[str, Any] = {"__file__": str(path), "__name__": "_confirmation_freeze_parent"}
    exec(compile(raw, str(path), "exec"), namespace)
    return type("Freeze", (), namespace)


def _committed_result(path: Path, commit: str, relative: str, label: str, expected_sha256: str | None = None) -> tuple[dict[str, Any], str]:
    raw = _stable(Path(path))
    if raw != _git_blob(commit, relative):
        raise ValueError(f"{label} result is not the exact committed Git blob")
    digest = sha256(raw)
    if expected_sha256 is not None and digest != expected_sha256:
        raise ValueError(f"{label} result commitment drifted")
    return _strict_raw(raw, f"{label} result"), digest


def _admit_evidence(*, grok_result_path: Path, grok_result_commit: str, sol_result_path: Path, sol_result_commit: str) -> dict[str, Any]:
    grok, grok_sha = _committed_result(grok_result_path, grok_result_commit, GROK_RESULT_RELATIVE, "Grok", GROK_RESULT_SHA256)
    selection = grok.get("selection")
    if (grok.get("study_id") != GROK_RESULT_ID or not isinstance(grok.get("authority"), Mapping)
            or grok["authority"].get("selection") != "grok_development_only"
            or not isinstance(selection, Mapping) or selection.get("candidate_id") != SELECTED):
        raise ValueError("Grok development selection does not admit the selected confirmation candidate")
    if sol_result_commit != SOL_RESULT_COMMIT:
        raise ValueError("Sol result commit drifted")
    sol, sol_sha = _committed_result(sol_result_path, sol_result_commit, SOL_RESULT_RELATIVE, "Sol", SOL_RESULT_SHA256)
    metrics = sol.get("metrics")
    comparison = sol.get("comparison")
    if (sol.get("study_id") != SOL_RESULT_ID or not isinstance(metrics, list) or not isinstance(comparison, Mapping)
            or {row.get("candidate_id") for row in metrics if isinstance(row, Mapping)} != {BASELINE, PARENT, SELECTED}):
        raise ValueError("Sol validation result does not contain the exact three-arm evidence")
    baseline_to_descendant = comparison.get("baseline_to_descendant")
    if (not isinstance(baseline_to_descendant, Mapping) or baseline_to_descendant.get("from_candidate_id") != BASELINE
            or baseline_to_descendant.get("to_candidate_id") != SELECTED
            or not isinstance(baseline_to_descendant.get("absolute_delta"), (int, float))
            or baseline_to_descendant["absolute_delta"] >= 0):
        raise ValueError("Sol validation does not independently support the selected candidate")
    return {"grok": {"study_id": GROK_RESULT_ID, "relative_path": GROK_RESULT_RELATIVE, "commit": grok_result_commit, "result_sha256": grok_sha, "result_internal_sha256": grok.get("result_internal_sha256"), "selected_candidate_id": SELECTED}, "sol": {"study_id": SOL_RESULT_ID, "relative_path": SOL_RESULT_RELATIVE, "commit": sol_result_commit, "result_sha256": sol_sha, "result_internal_sha256": sol.get("result_internal_sha256"), "validated_candidate_id": SELECTED}}


def _source_material(*, freeze: Any, normalized_root: Path, materialization_root: Path, frozen_successor_path: Path, hanna_csv_path: Path) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]], list[dict[str, Any]]]:
    if sha256(_stable(Path(frozen_successor_path))) != FROZEN_SUCCESSOR_SHA256:
        raise ValueError("frozen successor contract drifted")
    if sha256(_stable(Path(hanna_csv_path))) != HANNA_CSV_SHA256:
        raise ValueError("HANNA annotations drifted")
    materialization = strict_json(Path(materialization_root) / "materialization.json", "materialization")
    if sha256(canonical(materialization)) != MATERIALIZATION_SHA256 or materialization.get("provider_calls_made") != 0 or materialization.get("process_launches") != 0:
        raise ValueError("baseline materialization lineage drifted")
    artifacts = materialization.get("artifacts")
    instruction = _stable(Path(materialization_root) / "parent-instruction.bin")
    profile = _stable(Path(materialization_root) / "parent-profile.bin")
    if not isinstance(artifacts, Mapping) or artifacts.get("parent-instruction.bin") != sha256(instruction) or artifacts.get("parent-profile.bin") != sha256(profile):
        raise ValueError("baseline source bytes drifted")
    descendants = freeze.descendants(Path(normalized_root))
    selected = next((row for row in descendants if row.get("candidate_id") == SELECTED), None)
    if not isinstance(selected, Mapping):
        raise ValueError("selected descendant is absent from the pinned broader freeze")
    candidates = [
        {"candidate_id": BASELINE, "candidate_sha256": sha256({"candidate_id": BASELINE, "instruction_sha256": sha256(instruction), "profile_sha256": sha256(profile), "materialization_sha256": MATERIALIZATION_SHA256}), "instruction_bytes": instruction, "profile_bytes": profile, "instruction_sha256": sha256(instruction), "profile_sha256": sha256(profile), "kind": "immutable_baseline_materialization"},
        {key: selected[key] for key in ("candidate_id", "candidate_sha256", "instruction_bytes", "profile_bytes", "instruction_sha256", "profile_sha256", "parent_artifact_sha256", "kind", "factor", "addendum", "requested_step_fraction", "step_semantics")},
    ]
    v3 = freeze._v3()
    if sha256(_stable(freeze.V3_PATH)) != V3_SHA256:
        raise ValueError("pinned v3 source drifted")
    study, _harness, _frozen, split, _parents = v3._material(frozen_successor_path=Path(frozen_successor_path), hanna_csv_path=Path(hanna_csv_path))
    source_freeze = v3.v2_module().parent_modules()[2]
    sources = source_freeze._source_material(frozen_successor_path=Path(frozen_successor_path), hanna_csv_path=Path(hanna_csv_path))
    targets = v3.v2_module()._human_targets(study=study, frozen_successor_path=Path(frozen_successor_path), hanna_csv_path=Path(hanna_csv_path))
    partition_groups: dict[str, set[str]] = {"train": set(), "development": set(), "confirmation": set()}
    partition_counts: dict[str, int] = {"train": 0, "development": 0, "confirmation": 0}
    confirmation: list[dict[str, Any]] = []
    for row in split.get("items", []):
        if not isinstance(row, Mapping):
            raise ValueError("frozen split item drifted")
        partition, group, item = row.get("partition"), row.get("prompt_group_id"), row.get("item_id")
        if partition not in partition_groups or not isinstance(group, str) or not isinstance(item, str):
            raise ValueError("frozen split partition drifted")
        partition_groups[partition].add(group)
        partition_counts[partition] += 1
        if partition == "confirmation":
            source, target = sources.get(item), targets.get(item)
            if not isinstance(source, Mapping) or not isinstance(target, Mapping):
                raise ValueError("confirmation source or target reconstruction drifted")
            confirmation.append({"partition": partition, "prompt_group_id": group, "item_id": item, "target": {dimension: float(target[dimension]) for dimension in DIMENSIONS}, "source": source})
    if (partition_counts != {"train": 48, "development": 13, "confirmation": 19}
            or {key: len(value) for key, value in partition_groups.items()} != {"train": 24, "development": 7, "confirmation": 8}
            or any(partition_groups[left] & partition_groups[right] for left in partition_groups for right in partition_groups if left < right)):
        raise ValueError("frozen partition disjointness or confirmation geometry drifted")
    confirmation.sort(key=lambda row: (row["prompt_group_id"], row["item_id"]))
    return candidates, sources, confirmation


def _payload(source_freeze: Any, item: Mapping[str, Any], candidate: Mapping[str, Any]) -> bytes:
    inherited = source_freeze._payload_bytes(item=item, candidate=candidate)
    value = json.loads(inherited.decode("utf-8"))
    if value.get("study_id") != "hbq-human-alignment-optimizer-v1":
        raise ValueError("predecessor payload study identity drifted")
    value["study_id"] = STUDY_ID
    return canonical(value)


def _manifest(candidate: Mapping[str, Any]) -> dict[str, Any]:
    keys = ("candidate_id", "candidate_sha256", "instruction_sha256", "profile_sha256", "kind")
    value = {key: candidate[key] for key in keys}
    for key in ("parent_artifact_sha256", "factor", "addendum", "requested_step_fraction", "step_semantics"):
        if key in candidate:
            value[key] = candidate[key]
    value["manifest_sha256"] = sha256(value)
    return value


def contract() -> dict[str, Any]:
    return strict_json(HERE / "study-contract.json", "study contract")


def build(*, normalized_root: Path, materialization_root: Path, frozen_successor_path: Path, hanna_csv_path: Path, grok_result_path: Path, grok_result_commit: str, sol_result_path: Path, sol_result_commit: str) -> dict[str, Any]:
    freeze = _load_freeze()
    evidence = _admit_evidence(grok_result_path=Path(grok_result_path), grok_result_commit=grok_result_commit, sol_result_path=Path(sol_result_path), sol_result_commit=sol_result_commit)
    candidates, sources, confirmation = _source_material(freeze=freeze, normalized_root=Path(normalized_root), materialization_root=Path(materialization_root), frozen_successor_path=Path(frozen_successor_path), hanna_csv_path=Path(hanna_csv_path))
    source_freeze = freeze._v3().v2_module().parent_modules()[2]
    cells: list[dict[str, Any]] = []
    for item in confirmation:
        for candidate in candidates:
            payload = _payload(source_freeze, item["source"], candidate)
            identity = {"study_id": STUDY_ID, "candidate_id": candidate["candidate_id"], "prompt_group_id": item["prompt_group_id"], "item_id": item["item_id"]}
            cells.append({"ordinal": len(cells) + 1, "cell_id": "confirmation-" + sha256(identity)[:16], "candidate_id": candidate["candidate_id"], "candidate_sha256": candidate["candidate_sha256"], "candidate_instruction_sha256": candidate["instruction_sha256"], "candidate_profile_sha256": candidate["profile_sha256"], "partition": "confirmation", "prompt_group_id": item["prompt_group_id"], "item_id": item["item_id"], "target": item["target"], "payload_base64": base64.b64encode(payload).decode("ascii"), "payload_sha256": sha256(payload), "response_schema_sha256": sha256(canonical(json.loads(payload.decode("utf-8"))["response_schema"]))})
    if len(cells) != 38 or len({row["cell_id"] for row in cells}) != 38 or {row["candidate_id"] for row in cells} != {BASELINE, SELECTED}:
        raise ValueError("confirmation cell geometry drifted")
    groups = [{"partition": "confirmation", "prompt_group_id": group, "items": sum(row["prompt_group_id"] == group for row in confirmation)} for group in sorted({row["prompt_group_id"] for row in confirmation})]
    value = {"format_version": 1, "study_id": STUDY_ID, "kind": "frozen_provider_free_hanna_confirmation_schedule", "candidate_selection": {"selected_candidate_id": SELECTED, "control_candidate_id": BASELINE, "selection_evidence": evidence}, "source_commitments": {"broader_freeze_commit": FREEZE_COMMIT, "broader_freeze_sha256": FREEZE_SHA256, "v3_source_sha256": V3_SHA256, "frozen_successor_file_sha256": FROZEN_SUCCESSOR_SHA256, "hanna_csv_file_sha256": HANNA_CSV_SHA256, "materialization_file_sha256": MATERIALIZATION_SHA256}, "candidates": [_manifest(candidate) for candidate in candidates], "groups": groups, "cells": cells, "geometry": {"candidates": 2, "confirmation_groups": 8, "confirmation_items": 19, "endpoint_neutral_logical_cells": 38}, "authority": {"provider_calls_made": 0, "process_launches": 0, "selection": "frozen_from_committed_grok_plus_sol_evidence", "runtime": "none", "confirmation": {"status": "opened_by_this_frozen_schedule", "cells": 38}, "dspy_optuna_runtime": "forbidden"}}
    value["schedule_sha256"] = sha256(value)
    validate_schedule(value)
    return value


def validate_schedule(value: Mapping[str, Any]) -> None:
    body = dict(value)
    declared = body.pop("schedule_sha256", None)
    if not isinstance(declared, str) or sha256(body) != declared:
        raise ValueError("frozen schedule commitment drifted")
    geometry = value.get("geometry")
    cells, candidates, groups = value.get("cells"), value.get("candidates"), value.get("groups")
    if (value.get("study_id") != STUDY_ID or geometry != {"candidates": 2, "confirmation_groups": 8, "confirmation_items": 19, "endpoint_neutral_logical_cells": 38}
            or not isinstance(cells, list) or not isinstance(candidates, list) or not isinstance(groups, list)
            or len(cells) != 38 or len(candidates) != 2 or len(groups) != 8):
        raise ValueError("frozen confirmation geometry drifted")
    if {row.get("candidate_id") for row in candidates if isinstance(row, Mapping)} != {BASELINE, SELECTED}:
        raise ValueError("frozen candidate identity drifted")
    if any(not isinstance(row, Mapping) or row.get("partition") != "confirmation" for row in cells):
        raise ValueError("non-confirmation cell leaked into frozen schedule")
    if (any(not isinstance(group, Mapping) or not isinstance(group.get("prompt_group_id"), str) or not isinstance(group.get("items"), int) for group in groups)
            or len({row.get("item_id") for row in cells}) != 19 or len({row.get("prompt_group_id") for row in cells}) != 8
            or any(sum(row.get("candidate_id") == candidate for row in cells) != 19 for candidate in (BASELINE, SELECTED))
            or any(sum(row.get("prompt_group_id") == group["prompt_group_id"] for row in cells) != 2 * group["items"] for group in groups)):
        raise ValueError("frozen confirmation item or group geometry drifted")
    for row in cells:
        payload = base64.b64decode(row.get("payload_base64", ""), validate=True)
        target = row.get("target")
        if (sha256(payload) != row.get("payload_sha256") or json.loads(payload.decode("utf-8")).get("study_id") != STUDY_ID
                or not isinstance(target, Mapping) or set(target) != set(DIMENSIONS)):
            raise ValueError("frozen payload binding drifted")


def freeze(*, output_root: Path, **inputs: Any) -> dict[str, Any]:
    root = Path(output_root)
    if root.exists():
        raise ValueError("freeze output root must be fresh")
    schedule = build(**inputs)
    root.mkdir(parents=True)
    for candidate in schedule["candidates"]:
        (root / f"{candidate['candidate_id']}.json").write_bytes(canonical(candidate))
    (root / "schedule.json").write_bytes(canonical(schedule))
    validate_frozen_root(root)
    return schedule


def validate_frozen_root(root: Path) -> dict[str, Any]:
    root = Path(root)
    _plain(root, directory=True)
    schedule_path = root / "schedule.json"
    _plain(schedule_path, directory=False)
    schedule = strict_json(schedule_path, "persisted schedule")
    validate_schedule(schedule)
    expected = {"schedule.json", *(f"{candidate['candidate_id']}.json" for candidate in schedule["candidates"])}
    if {path.name for path in root.iterdir()} != expected:
        raise ValueError("persisted root inventory drifted")
    for candidate in schedule["candidates"]:
        path = root / f"{candidate['candidate_id']}.json"
        _plain(path, directory=False)
        persisted = strict_json(path, "persisted candidate manifest")
        if persisted != candidate:
            raise ValueError("persisted candidate manifest drifted")
    return schedule


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--normalized-root", required=True)
    parser.add_argument("--materialization-root", required=True)
    parser.add_argument("--frozen-successor-path", required=True)
    parser.add_argument("--hanna-csv-path", required=True)
    parser.add_argument("--grok-result-path", required=True)
    parser.add_argument("--grok-result-commit", default=GROK_RESULT_COMMIT)
    parser.add_argument("--sol-result-path", required=True)
    parser.add_argument("--sol-result-commit", default=SOL_RESULT_COMMIT)
    args = parser.parse_args()
    schedule = freeze(output_root=Path(args.output_root), normalized_root=Path(args.normalized_root), materialization_root=Path(args.materialization_root), frozen_successor_path=Path(args.frozen_successor_path), hanna_csv_path=Path(args.hanna_csv_path), grok_result_path=Path(args.grok_result_path), grok_result_commit=args.grok_result_commit, sol_result_path=Path(args.sol_result_path), sol_result_commit=args.sol_result_commit)
    print(json.dumps({"schedule_sha256": schedule["schedule_sha256"], "geometry": schedule["geometry"], "provider_calls_made": 0}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
