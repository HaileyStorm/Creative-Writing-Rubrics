"""Score-blind HANNA96 public validation split and private unopened freeze."""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import os
import secrets
import tempfile
from collections import defaultdict
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
CONTRACT_PATH = HERE / "study-contract.json"
MANIFEST_PATH = HERE / "manifest.json"
PRIVATE_FILENAME = "private-freeze.json"
DIMENSIONS = ("Relevance", "Coherence", "Empathy", "Surprise", "Engagement", "Complexity")
CSV_FIELDS = {"Story ID", "Prompt", "Human", "Story", "Model", *DIMENSIONS, "Worker ID", "Assignment ID", "Work time in seconds", "Name"}
PRIVATE_PARTITIONS = ("future_confirmation", "reserve")


def canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def sha256(value: Any) -> str:
    return hashlib.sha256(value if isinstance(value, bytes) else canonical(value)).hexdigest()


def _exact(value: Mapping[str, Any], keys: set[str], label: str) -> None:
    if not isinstance(value, Mapping) or set(value) != keys:
        raise ValueError(f"HANNA96 {label} has missing, extra, or unsafe keys")


def _read_json_bytes(path: Path, label: str, *, canonical_required: bool = True) -> tuple[dict[str, Any], bytes]:
    try:
        raw = Path(path).read_bytes()
        value = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"HANNA96 {label} cannot be read") from exc
    if not isinstance(value, dict):
        raise TypeError(f"HANNA96 {label} must be an object")
    if canonical_required and raw != canonical(value) + b"\n":
        raise ValueError(f"HANNA96 {label} is not canonical JSON")
    return value, raw


def load_contract() -> dict[str, Any]:
    contract, _ = _read_json_bytes(CONTRACT_PATH, "contract", canonical_required=False)
    _exact(contract, {"format_version", "study_id", "kind", "dataset", "fresh88", "selection", "partitions", "outputs", "interpretation_limits"}, "contract")
    if contract["format_version"] != 1 or contract["study_id"] != "hbq-human-alignment-hanna96-fresh-split-v1" or contract["kind"] != "score_blind_residual_hanna_split" or contract["outputs"] != ["manifest.json"]:
        raise ValueError("HANNA96 contract identity drifted")
    dataset = contract["dataset"]
    _exact(dataset, {"repository", "upstream_commit", "csv_name", "csv_git_blob_oid_sha1", "csv_bytes", "csv_sha256", "license"}, "dataset")
    if dataset != {
        "repository": "https://github.com/dig-team/hanna-benchmark-asg",
        "upstream_commit": "282f27536a5d05ad4ce14298abcd70c45668fed2",
        "csv_name": "hanna_stories_annotations.csv",
        "csv_git_blob_oid_sha1": "2eec3bbf5b1363a998dbf73199228e4fe13405ca",
        "csv_bytes": 13219167,
        "csv_sha256": "ef59054d27fa32def06cfdc57243b1dd09c7e71f40b6d9d43fecfbf60e59026b",
        "license": "MIT",
    }:
        raise ValueError("HANNA96 dataset pin drifted")
    fresh = contract["fresh88"]
    _exact(fresh, {"study_id", "contract_path", "contract_sha256", "group_count", "group_ids", "group_ids_sha256"}, "Fresh88 pin")
    if fresh["study_id"] != "hbq-human-alignment-optimizer-v1" or fresh["contract_path"] != "evaluation-results/hbq-human-alignment-optimizer-v1/study-contract.json" or fresh["group_count"] != 39 or not isinstance(fresh["group_ids"], list) or fresh["group_ids"] != sorted(set(fresh["group_ids"])) or len(fresh["group_ids"]) != 39 or sha256(fresh["group_ids"]) != fresh["group_ids_sha256"] or not all(isinstance(value, str) and len(value) == 64 for value in (fresh["contract_sha256"], fresh["group_ids_sha256"])):
        raise ValueError("HANNA96 Fresh88 pin drifted")
    selection = contract["selection"]
    _exact(selection, {"public_seed", "public_group_rank", "private_group_and_story_rank", "selected_items_per_group", "score_access"}, "selection")
    if selection != {
        "public_seed": "hanna96-fresh-split-v1|202608311",
        "public_group_rank": "sha256(public_seed + '|' + prompt_group_id)",
        "private_group_and_story_rank": "sha256(private_seed + '|' + prompt_group_id [+ '|' + story_id])",
        "selected_items_per_group": 2,
        "score_access": "aggregate six-dimension annotations only after deterministic story selection",
    }:
        raise ValueError("HANNA96 selection rule drifted")
    partitions = contract["partitions"]
    _exact(partitions, {"validation", "future_confirmation", "reserve"}, "partitions")
    if partitions != {
        "validation": {"group_count": 16, "item_count": 32, "status": "open"},
        "future_confirmation": {"group_count": 16, "item_count": 32, "status": "privately_frozen_unopened"},
        "reserve": {"group_count": 25, "item_count": 50, "status": "privately_frozen_unopened"},
    }:
        raise ValueError("HANNA96 partition rule drifted")
    if not isinstance(contract["interpretation_limits"], list) or not all(isinstance(value, str) for value in contract["interpretation_limits"]):
        raise ValueError("HANNA96 limits drifted")
    return contract


CONTRACT = load_contract()


def prompt_group_id(prompt: str) -> str:
    if not isinstance(prompt, str):
        raise TypeError("HANNA96 prompt is malformed")
    return "prompt-" + hashlib.sha256(prompt.encode()).hexdigest()[:16]


def _rows_from_bytes(raw: bytes) -> list[dict[str, str]]:
    try:
        rows = list(csv.DictReader(io.StringIO(raw.decode("utf-8-sig"))))
    except (UnicodeDecodeError, csv.Error) as exc:
        raise ValueError("HANNA96 CSV cannot be read") from exc
    if not rows or set(rows[0]) != CSV_FIELDS or any(set(row) != CSV_FIELDS for row in rows):
        raise ValueError("HANNA96 CSV schema drifted")
    return rows


def read_source(csv_path: Path) -> list[dict[str, str]]:
    try:
        raw = Path(csv_path).read_bytes()
    except OSError as exc:
        raise ValueError("HANNA96 CSV cannot be read") from exc
    dataset = CONTRACT["dataset"]
    if len(raw) != dataset["csv_bytes"] or hashlib.sha256(raw).hexdigest() != dataset["csv_sha256"]:
        raise ValueError("HANNA96 CSV source pin drifted")
    return _rows_from_bytes(raw)


def _source_groups(rows: Iterable[Mapping[str, str]]) -> dict[str, dict[str, Any]]:
    groups: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not all(isinstance(row.get(field), str) for field in CSV_FIELDS):
            raise ValueError("HANNA96 CSV row is malformed")
        group_id = prompt_group_id(row["Prompt"])
        group = groups.setdefault(group_id, {"prompt": row["Prompt"], "rows": []})
        if group["prompt"] != row["Prompt"]:
            raise ValueError("HANNA96 prompt collision detected")
        group["rows"].append(dict(row))
    if len(groups) != 96:
        raise ValueError("HANNA96 source prompt-group geometry drifted")
    return groups


def _residual_groups(groups: Mapping[str, Any]) -> list[str]:
    fresh = CONTRACT["fresh88"]["group_ids"]
    if not set(fresh).issubset(groups):
        raise ValueError("HANNA96 Fresh88 groups are not present in source")
    residual = sorted(set(groups) - set(fresh))
    if len(residual) != 57 or set(residual) & set(fresh):
        raise ValueError("HANNA96 residual groups overlap Fresh88")
    return residual


def _rank(seed: str, group_id: str, story_id: str | None = None) -> tuple[str, str]:
    suffix = f"{seed}|{group_id}" if story_id is None else f"{seed}|{group_id}|{story_id}"
    return hashlib.sha256(suffix.encode()).hexdigest(), story_id or group_id


def _public_validation_groups(residual_group_ids: list[str]) -> list[str]:
    ranked = sorted(residual_group_ids, key=lambda group_id: _rank(CONTRACT["selection"]["public_seed"], group_id))
    if len(ranked) != 57 or len(set(ranked)) != 57:
        raise ValueError("HANNA96 residual group geometry drifted")
    return ranked[:16]


def _finite_target(rows: list[Mapping[str, str]]) -> dict[str, float]:
    if len(rows) != 3:
        raise ValueError("HANNA96 selected story does not have exactly three annotations")
    target: dict[str, float] = {}
    for dimension in DIMENSIONS:
        values: list[float] = []
        for row in rows:
            try:
                value = float(row[dimension])
            except (TypeError, ValueError) as exc:
                raise ValueError("HANNA96 annotation is not finite") from exc
            if not math.isfinite(value):
                raise ValueError("HANNA96 annotation is not finite")
            values.append(value)
        target[dimension] = sum(values) / 3
    return target


def _selected_group_records(groups: Mapping[str, Mapping[str, Any]], group_ids: Iterable[str], *, seed: str, partition: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    group_records: list[dict[str, Any]] = []
    items: list[dict[str, Any]] = []
    status = CONTRACT["partitions"][partition]["status"]
    for group_id in sorted(group_ids):
        group = groups[group_id]
        by_story: dict[str, list[Mapping[str, str]]] = defaultdict(list)
        for row in group["rows"]:
            by_story[row["Story ID"]].append(row)
        candidates: list[tuple[str, str, list[Mapping[str, str]]]] = []
        for story_id, story_rows in by_story.items():
            models = {row["Model"] for row in story_rows}
            stories = {row["Story"] for row in story_rows}
            if len(models) != 1 or len(stories) != 1:
                raise ValueError("HANNA96 story model binding drifted")
            model = next(iter(models))
            if model != "Human":
                candidates.append((story_id, model, story_rows))
        candidates.sort(key=lambda value: _rank(seed, group_id, value[0]))
        if len(candidates) < CONTRACT["selection"]["selected_items_per_group"]:
            raise ValueError("HANNA96 residual group has too few generated stories")
        chosen = candidates[:CONTRACT["selection"]["selected_items_per_group"]]
        group_records.append({"prompt_group_id": group_id, "partition": partition, "status": status, "prompt_sha256": hashlib.sha256(group["prompt"].encode()).hexdigest(), "selected_story_ids": [value[0] for value in chosen]})
        for story_id, model, story_rows in chosen:
            items.append({
                "item_id": "item-" + hashlib.sha256(story_id.encode()).hexdigest()[:16],
                "prompt_group_id": group_id,
                "partition": partition,
                "status": status,
                "story_id": story_id,
                "model": model,
                "prompt": group["prompt"],
                "story": story_rows[0]["Story"],
                "annotation_count": 3,
                "target": _finite_target(story_rows),
                "source_binding_sha256": sha256({"prompt_group_id": group_id, "story_id": story_id, "model": model, "prompt": group["prompt"], "story": story_rows[0]["Story"]}),
            })
    items.sort(key=lambda item: item["item_id"])
    expected_count = CONTRACT["partitions"][partition]["item_count"]
    if len(group_records) != CONTRACT["partitions"][partition]["group_count"] or len(items) != expected_count or len({item["item_id"] for item in items}) != expected_count:
        raise ValueError("HANNA96 selected item geometry drifted")
    return group_records, items


def make_private_freeze_from_rows(rows: Iterable[Mapping[str, str]], *, private_seed: str) -> dict[str, Any]:
    if not isinstance(private_seed, str) or len(private_seed) != 64 or any(character not in "0123456789abcdef" for character in private_seed):
        raise ValueError("HANNA96 private seed is malformed")
    groups = _source_groups(rows)
    residual = _residual_groups(groups)
    validation = _public_validation_groups(residual)
    remaining = sorted(set(residual) - set(validation))
    ranked = sorted(remaining, key=lambda group_id: _rank(private_seed, group_id))
    partitions = {"future_confirmation": ranked[:16], "reserve": ranked[16:]}
    if len(remaining) != 41 or any(len(partitions[name]) != CONTRACT["partitions"][name]["group_count"] for name in PRIVATE_PARTITIONS):
        raise ValueError("HANNA96 private partition geometry drifted")
    group_records: list[dict[str, Any]] = []
    selected_items: list[dict[str, Any]] = []
    for partition in PRIVATE_PARTITIONS:
        records, items = _selected_group_records(groups, partitions[partition], seed=private_seed, partition=partition)
        group_records.extend(records)
        selected_items.extend(items)
    group_records.sort(key=lambda record: record["prompt_group_id"])
    selected_items.sort(key=lambda item: item["item_id"])
    return {
        "format_version": 1,
        "study_id": "hbq-human-alignment-hanna96-fresh-split-v1-private-freeze",
        "dataset": CONTRACT["dataset"],
        "fresh88_group_ids_sha256": CONTRACT["fresh88"]["group_ids_sha256"],
        "public_validation_group_ids_sha256": sha256(sorted(validation)),
        "private_seed": private_seed,
        "partitions": {name: {"group_ids": sorted(group_ids), "status": CONTRACT["partitions"][name]["status"]} for name, group_ids in partitions.items()},
        "groups": group_records,
        "selected_items": selected_items,
        "commitments": {"residual_group_ids_sha256": sha256(residual), "private_group_ids_sha256": sha256(sorted(remaining)), "groups_sha256": sha256(group_records), "selected_item_ids_sha256": sha256([item["item_id"] for item in selected_items]), "selected_items_sha256": sha256(selected_items)},
    }


def _validate_private_freeze(value: Mapping[str, Any], rows: Iterable[Mapping[str, str]]) -> None:
    _exact(value, {"format_version", "study_id", "dataset", "fresh88_group_ids_sha256", "public_validation_group_ids_sha256", "private_seed", "partitions", "groups", "selected_items", "commitments"}, "private freeze")
    if value["format_version"] != 1 or value["study_id"] != "hbq-human-alignment-hanna96-fresh-split-v1-private-freeze":
        raise ValueError("HANNA96 private freeze identity drifted")
    if value != make_private_freeze_from_rows(rows, private_seed=value["private_seed"]):
        raise ValueError("HANNA96 private freeze is not the exact score-blind derivation")


def _private_freeze(path: Path, rows: Iterable[Mapping[str, str]]) -> tuple[dict[str, Any], str]:
    value, raw = _read_json_bytes(path, "private freeze")
    _validate_private_freeze(value, rows)
    return value, hashlib.sha256(raw).hexdigest()


def derive_manifest_from_rows(rows: Iterable[Mapping[str, str]], *, private_freeze_sha256: str) -> dict[str, Any]:
    if not isinstance(private_freeze_sha256, str) or len(private_freeze_sha256) != 64:
        raise ValueError("HANNA96 private freeze commitment is malformed")
    groups = _source_groups(rows)
    residual = _residual_groups(groups)
    validation = _public_validation_groups(residual)
    group_records, selected_items = _selected_group_records(groups, validation, seed=CONTRACT["selection"]["public_seed"], partition="validation")
    private_group_count = sum(CONTRACT["partitions"][name]["group_count"] for name in PRIVATE_PARTITIONS)
    private_item_count = sum(CONTRACT["partitions"][name]["item_count"] for name in PRIVATE_PARTITIONS)
    return {
        "format_version": 1,
        "study_id": CONTRACT["study_id"],
        "dataset": CONTRACT["dataset"],
        "fresh88": {"study_id": CONTRACT["fresh88"]["study_id"], "group_ids": CONTRACT["fresh88"]["group_ids"], "group_ids_sha256": CONTRACT["fresh88"]["group_ids_sha256"]},
        "selection": {"public_seed": CONTRACT["selection"]["public_seed"], "public_group_rank": CONTRACT["selection"]["public_group_rank"], "selected_items_per_group": CONTRACT["selection"]["selected_items_per_group"], "score_access": CONTRACT["selection"]["score_access"]},
        "partitions": {
            "validation": {"group_ids": sorted(validation), "status": CONTRACT["partitions"]["validation"]["status"]},
            "future_confirmation": {"group_count": CONTRACT["partitions"]["future_confirmation"]["group_count"], "item_count": CONTRACT["partitions"]["future_confirmation"]["item_count"], "status": CONTRACT["partitions"]["future_confirmation"]["status"]},
            "reserve": {"group_count": CONTRACT["partitions"]["reserve"]["group_count"], "item_count": CONTRACT["partitions"]["reserve"]["item_count"], "status": CONTRACT["partitions"]["reserve"]["status"]},
        },
        "groups": group_records,
        "selected_items": selected_items,
        "commitments": {"all_prompt_group_ids_sha256": sha256(sorted(groups)), "fresh88_group_ids_sha256": CONTRACT["fresh88"]["group_ids_sha256"], "residual_group_ids_sha256": sha256(residual), "validation_group_ids_sha256": sha256(sorted(validation)), "groups_sha256": sha256(group_records), "selected_item_ids_sha256": sha256([item["item_id"] for item in selected_items]), "selected_items_sha256": sha256(selected_items), "private_freeze_sha256": private_freeze_sha256, "private_frozen_group_count": private_group_count, "private_frozen_item_count": private_item_count},
        "interpretation_limits": CONTRACT["interpretation_limits"],
    }


def validate_manifest(value: Mapping[str, Any], *, rows: Iterable[Mapping[str, str]], private_freeze_sha256: str) -> None:
    _exact(value, {"format_version", "study_id", "dataset", "fresh88", "selection", "partitions", "groups", "selected_items", "commitments", "interpretation_limits"}, "manifest")
    if value != derive_manifest_from_rows(rows, private_freeze_sha256=private_freeze_sha256):
        raise ValueError("HANNA96 manifest is not the exact public derivation")


def _write_canonical(path: Path, value: Mapping[str, Any], *, overwrite: bool) -> str:
    target = Path(path)
    if target.exists() and not overwrite:
        raise ValueError("Refusing to overwrite an existing HANNA96 artifact")
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = canonical(value) + b"\n"
    handle, temporary = tempfile.mkstemp(prefix=f".{target.name}.", dir=target.parent)
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write(payload)
        os.replace(temporary, target)
    except BaseException:
        if os.path.exists(temporary):
            os.unlink(temporary)
        raise
    return hashlib.sha256(payload).hexdigest()


def freeze_private_file(*, csv_path: Path, private_root: Path, private_seed: str | None = None) -> str:
    root = Path(private_root)
    if root.exists():
        raise ValueError("Refusing to merge into an existing HANNA96 private freeze root")
    freeze = make_private_freeze_from_rows(read_source(csv_path), private_seed=private_seed or secrets.token_hex(32))
    try:
        root.mkdir()
    except OSError as exc:
        raise ValueError("HANNA96 private freeze root cannot be created") from exc
    try:
        return _write_canonical(root / PRIVATE_FILENAME, freeze, overwrite=False)
    except BaseException:
        try:
            root.rmdir()
        except OSError:
            pass
        raise


def _public_manifest_from_files(*, csv_path: Path, private_root: Path) -> tuple[dict[str, Any], str]:
    rows = read_source(csv_path)
    _, private_digest = _private_freeze(Path(private_root) / PRIVATE_FILENAME, rows)
    return derive_manifest_from_rows(rows, private_freeze_sha256=private_digest), private_digest


def build_public_manifest_file(*, csv_path: Path, private_root: Path, output_path: Path, overwrite: bool = False) -> tuple[str, str]:
    manifest, private_digest = _public_manifest_from_files(csv_path=csv_path, private_root=private_root)
    return _write_canonical(output_path, manifest, overwrite=overwrite), private_digest


def verify_manifest_file(*, csv_path: Path, private_root: Path, manifest_path: Path = MANIFEST_PATH) -> tuple[str, str]:
    rows = read_source(csv_path)
    _, private_digest = _private_freeze(Path(private_root) / PRIVATE_FILENAME, rows)
    value, raw = _read_json_bytes(manifest_path, "manifest")
    validate_manifest(value, rows=rows, private_freeze_sha256=private_digest)
    return hashlib.sha256(raw).hexdigest(), private_digest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_mutually_exclusive_group(required=True)
    commands.add_argument("--freeze-private", action="store_true")
    commands.add_argument("--build-public", action="store_true")
    commands.add_argument("--rebuild-public", action="store_true")
    commands.add_argument("--verify", action="store_true")
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--private-root", required=True, type=Path)
    parser.add_argument("--output", type=Path, default=MANIFEST_PATH)
    args = parser.parse_args(argv)
    if args.freeze_private:
        print(json.dumps({"private_freeze_sha256": freeze_private_file(csv_path=args.source, private_root=args.private_root)}, sort_keys=True))
    elif args.verify:
        manifest_digest, private_digest = verify_manifest_file(csv_path=args.source, private_root=args.private_root, manifest_path=args.output)
        print(json.dumps({"manifest": args.output.name, "manifest_sha256": manifest_digest, "private_freeze_sha256": private_digest}, sort_keys=True))
    else:
        manifest_digest, private_digest = build_public_manifest_file(csv_path=args.source, private_root=args.private_root, output_path=args.output, overwrite=args.rebuild_public)
        print(json.dumps({"manifest": args.output.name, "manifest_sha256": manifest_digest, "private_freeze_sha256": private_digest}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
