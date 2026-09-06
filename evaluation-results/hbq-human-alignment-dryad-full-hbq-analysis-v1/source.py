"""Provider-free preparation and verification of the frozen Dryad human targets."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import re
import stat
import subprocess
from collections import defaultdict
from fractions import Fraction
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
REPOSITORY = ROOT.parents[1]
PROTOCOL_PATH = ROOT / "protocol.json"
PROTOCOL_SHA256 = "f6cf28247f8759a8a823bbdfb7f94e0af33a2661b9ffeb0ce17a1099662c7441"
PARTITIONS = ("TRAIN", "DEV", "CONFIRMATION")
OPEN_PARTITIONS = ("TRAIN", "DEV")
AXES = (
    "novel", "original", "rare", "appropriate", "feasible", "publishable",
    "well_written", "enjoyed", "boring", "funny", "twist", "future",
)
REQUIRED_CSV_FIELDS = ("evaluator_index", "story_slot", "story_id", "condition", "topic", "story_text", *AXES)


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def canonical_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _fraction(value: Fraction) -> dict[str, int]:
    return {"numerator": value.numerator, "denominator": value.denominator}


def _read_pinned(path: Path, expected_sha256: str) -> bytes:
    raw = path.read_bytes()
    if sha256_bytes(raw) != expected_sha256:
        raise ValueError(f"Pinned source hash drift: {path.name}")
    return raw


def _assert_unchanged(captured: dict[Path, bytes]) -> None:
    if any(path.read_bytes() != raw for path, raw in captured.items()):
        raise ValueError("Pinned source changed during preparation")


def _load_protocol() -> tuple[dict[str, Any], bytes]:
    raw = _read_pinned(PROTOCOL_PATH, PROTOCOL_SHA256)
    protocol = json.loads(raw)
    source = protocol.get("source")
    if not isinstance(source, dict) or tuple(source.get("axes", ())) != AXES:
        raise ValueError("Protocol source-axis contract drift")
    if protocol.get("execution", {}).get("provider_calls_authorized_by_this_file") is not False:
        raise ValueError("Protocol provider boundary drift")
    _assert_unchanged({PROTOCOL_PATH: raw})
    return protocol, raw


def _expected_counts(value: dict[str, Any]) -> dict[str, int]:
    if set(value) != set(PARTITIONS) or any(type(value[name]) is not int or value[name] < 0 for name in PARTITIONS):
        raise ValueError("Partition-count contract drift")
    return {name: value[name] for name in PARTITIONS}


def _split_index(records: list[dict[str, Any]], expected_counts: dict[str, int]) -> dict[str, dict[str, str]]:
    counts = {partition: 0 for partition in PARTITIONS}
    by_source: dict[str, dict[str, str]] = {}
    opaque_ids: set[str] = set()
    for record in records:
        if not isinstance(record, dict):
            raise ValueError("Split record is not an object")
        source_id, opaque_id, partition = (record.get(name) for name in ("source_story_id", "opaque_story_id", "partition"))
        if not all(isinstance(value, str) and value for value in (source_id, opaque_id, partition)):
            raise ValueError("Split identity schema drift")
        if partition not in PARTITIONS or source_id in by_source or opaque_id in opaque_ids:
            raise ValueError("Split identity or partition drift")
        by_source[source_id] = {"opaque_story_id": opaque_id, "partition": partition}
        opaque_ids.add(opaque_id)
        counts[partition] += 1
    if counts != expected_counts:
        raise ValueError("Split partition-count drift")
    return by_source


def derive_targets(ratings_raw: bytes, split_records: list[dict[str, Any]], expected_counts: dict[str, int]) -> dict[str, list[dict[str, Any]]]:
    """Derive only the open-partition, opaque story targets from pinned raw inputs."""
    counts = _expected_counts(expected_counts)
    split_by_source = _split_index(split_records, counts)
    try:
        text = ratings_raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError as error:
        raise ValueError("Ratings CSV is not strict UTF-8") from error
    reader = csv.reader(io.StringIO(text, newline=""))
    try:
        header = next(reader)
    except StopIteration as error:
        raise ValueError("Ratings CSV is empty") from error
    if len(header) != len(REQUIRED_CSV_FIELDS) or set(header) != set(REQUIRED_CSV_FIELDS):
        raise ValueError("Ratings CSV header drift")
    positions = {field: header.index(field) for field in REQUIRED_CSV_FIELDS}
    ratings: dict[str, dict[str, list[int]]] = defaultdict(lambda: {axis: [] for axis in AXES})
    slots: set[tuple[str, str]] = set()
    for row in reader:
        if len(row) != len(header):
            raise ValueError("Ratings CSV row width drift")
        story_id = row[positions["story_id"]]
        split = split_by_source.get(story_id)
        if split is None:
            raise ValueError("Ratings row has an unknown story ID")
        if split["partition"] == "CONFIRMATION":
            continue
        evaluator, slot = row[positions["evaluator_index"]], row[positions["story_slot"]]
        if not evaluator or not slot or (evaluator, slot) in slots:
            raise ValueError("Open evaluator-slot coverage drift")
        slots.add((evaluator, slot))
        story_ratings = ratings[story_id]
        for axis in AXES:
            value = row[positions[axis]]
            if value not in {"1", "2", "3", "4", "5", "6", "7", "8", "9"}:
                raise ValueError(f"Open rating is not an integer in range for {axis}")
            story_ratings[axis].append(int(value))
    open_sources = {source_id for source_id, record in split_by_source.items() if record["partition"] in OPEN_PARTITIONS}
    if set(ratings) != open_sources:
        raise ValueError("Open-story rating coverage drift")
    targets: dict[str, list[dict[str, Any]]] = {partition: [] for partition in OPEN_PARTITIONS}
    for source_id, record in split_by_source.items():
        partition = record["partition"]
        if partition == "CONFIRMATION":
            continue
        axis_means = {axis: Fraction(sum(ratings[source_id][axis]), len(ratings[source_id][axis])) for axis in AXES}
        rating_count = len(ratings[source_id][AXES[0]])
        if rating_count == 0 or any(len(ratings[source_id][axis]) != rating_count for axis in AXES):
            raise ValueError("Open-story axis coverage drift")
        targets[partition].append(
            {
                "opaque_story_id": record["opaque_story_id"],
                "partition": partition,
                "rating_count": rating_count,
                "axis_means": {axis: _fraction(axis_means[axis]) for axis in AXES},
                "indices": {
                    "novelty": _fraction(sum((axis_means[axis] for axis in ("novel", "original", "rare")), Fraction(0)) / 3),
                    "usefulness": _fraction(sum((axis_means[axis] for axis in ("appropriate", "feasible", "publishable")), Fraction(0)) / 3),
                },
            }
        )
    for partition in OPEN_PARTITIONS:
        if len(targets[partition]) != counts[partition]:
            raise ValueError("Open target count drift")
        targets[partition].sort(key=lambda record: str(record["opaque_story_id"]))
    return targets


def _read_jsonl(raw: bytes) -> list[dict[str, Any]]:
    try:
        lines = raw.decode("utf-8", errors="strict").splitlines()
        if any(not line for line in lines):
            raise ValueError("Split JSONL contains an empty line")
        return [json.loads(line) for line in lines]
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("Split manifest is not strict JSONL") from error


def _source_inputs(ratings_path: Path, freeze_root: Path) -> tuple[dict[str, Any], bytes, bytes, bytes, bytes, list[dict[str, Any]]]:
    protocol, protocol_raw = _load_protocol()
    source = protocol["source"]
    ratings_raw = _read_pinned(ratings_path, str(source["ratings_sha256"]))
    split_path = freeze_root / "split-manifest.jsonl"
    provenance_path = freeze_root / "provenance.json"
    split_raw = _read_pinned(split_path, str(source["split_sha256"]))
    parent_raw = _read_pinned(provenance_path, str(source["parent_provenance_sha256"]))
    records = _read_jsonl(split_raw)
    try:
        parent = json.loads(parent_raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("Parent provenance is not strict JSON") from error
    parent_split = parent.get("artifacts", {}).get("split-manifest.jsonl", {}) if isinstance(parent, dict) else {}
    if parent_split.get("sha256") != source["split_sha256"]:
        raise ValueError("Parent provenance split binding drift")
    _assert_unchanged({PROTOCOL_PATH: protocol_raw, ratings_path: ratings_raw, split_path: split_raw, provenance_path: parent_raw})
    return protocol, protocol_raw, ratings_raw, split_raw, parent_raw, records


def _generator_identity(commit: str | None = None) -> dict[str, str]:
    source_path = Path(__file__).resolve()
    captured = {source_path: source_path.read_bytes(), PROTOCOL_PATH: PROTOCOL_PATH.read_bytes()}
    if commit is None:
        result = subprocess.run(["git", "-C", str(REPOSITORY), "rev-parse", "HEAD"], capture_output=True, check=False)
        commit = result.stdout.decode("ascii", errors="strict").strip() if not result.returncode else ""
    if re.fullmatch(r"[0-9a-f]{40}", commit or "") is None:
        raise ValueError("Invalid recorded generator commit")
    for path, raw in captured.items():
        relative = path.relative_to(REPOSITORY).as_posix()
        result = subprocess.run(["git", "-C", str(REPOSITORY), "show", f"{commit}:{relative}"], capture_output=True, check=False)
        if result.returncode or result.stdout != raw:
            raise ValueError("Production preparation requires source and protocol committed byte-exactly at HEAD")
    _assert_unchanged(captured)
    return {
        "evidence_class": "committed_source",
        "git_commit": commit,
        "source_path": source_path.relative_to(REPOSITORY).as_posix(),
        "source_sha256": sha256_bytes(captured[source_path]),
        "contract_path": PROTOCOL_PATH.relative_to(REPOSITORY).as_posix(),
        "contract_sha256": sha256_bytes(captured[PROTOCOL_PATH]),
    }


def _expected_artifacts(ratings_path: Path, freeze_root: Path, *, generator_commit: str | None = None) -> dict[str, bytes]:
    protocol, protocol_raw, ratings_raw, split_raw, parent_raw, records = _source_inputs(ratings_path, freeze_root)
    source = protocol["source"]
    counts = _expected_counts(source["partitions"])
    targets = derive_targets(ratings_raw, records, counts)
    train_bytes = canonical_json_bytes(targets["TRAIN"])
    dev_bytes = canonical_json_bytes(targets["DEV"])
    generator = _generator_identity(generator_commit)
    provenance = {
        "schema_version": 1,
        "evidence_class": "provider_free_dryad_human_target_preparation",
        "generator": generator,
        "contract": {"path": PROTOCOL_PATH.relative_to(REPOSITORY).as_posix(), "sha256": sha256_bytes(protocol_raw)},
        "source": {
            "ratings_sha256": sha256_bytes(ratings_raw),
            "split_manifest_sha256": sha256_bytes(split_raw),
            "parent_provenance_sha256": sha256_bytes(parent_raw),
        },
        "counts": {partition: counts[partition] for partition in PARTITIONS},
        "artifacts": {
            "train-targets.json": {"sha256": sha256_bytes(train_bytes), "bytes": len(train_bytes)},
            "dev-targets.json": {"sha256": sha256_bytes(dev_bytes), "bytes": len(dev_bytes)},
        },
        "provider_calls": 0,
        "metric_eligible": False,
    }
    _assert_unchanged({PROTOCOL_PATH: protocol_raw, ratings_path: ratings_raw, freeze_root / "split-manifest.jsonl": split_raw, freeze_root / "provenance.json": parent_raw})
    return {"train-targets.json": train_bytes, "dev-targets.json": dev_bytes, "provenance.json": canonical_json_bytes(provenance)}


def _external_output(ratings_path: Path, freeze_root: Path, output_root: Path) -> Path:
    def plain(path: Path) -> Path:
        absolute = Path(os.path.abspath(path))
        for candidate in (absolute, *absolute.parents):
            try:
                info = candidate.lstat()
            except FileNotFoundError:
                continue
            if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
                raise ValueError("Target/source path contains a link or reparse point")
        return absolute.resolve()

    destination = plain(output_root)
    for source in (REPOSITORY, ROOT, PROTOCOL_PATH.parent, freeze_root, ratings_path.parent):
        protected = plain(source)
        if destination.is_relative_to(protected) or protected.is_relative_to(destination):
            raise ValueError("Target output must be disjoint from repository and immutable source directories")
    return destination


def prepare(ratings_path: Path, freeze_root: Path, output_root: Path) -> dict[str, str]:
    """Create the three target artifacts in a fresh external directory only."""
    output_root = _external_output(ratings_path, freeze_root, output_root)
    artifacts = _expected_artifacts(ratings_path, freeze_root)
    _external_output(ratings_path, freeze_root, output_root)
    output_root.mkdir(parents=True, exist_ok=False)
    for name, raw in artifacts.items():
        with (output_root / name).open("xb") as stream:
            stream.write(raw)
    return {name: sha256_bytes(raw) for name, raw in artifacts.items()}


def verify(ratings_path: Path, freeze_root: Path, output_root: Path) -> dict[str, str]:
    provenance_path = output_root / "provenance.json"
    try:
        provenance = json.loads(provenance_path.read_bytes())
        commit = provenance["generator"]["git_commit"]
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError) as error:
        raise ValueError("Target provenance is malformed") from error
    artifacts = _expected_artifacts(ratings_path, freeze_root, generator_commit=commit)
    if not output_root.is_dir() or {path.name for path in output_root.iterdir()} != set(artifacts):
        raise ValueError("Target artifact inventory drift")
    for name, raw in artifacts.items():
        path = output_root / name
        if not path.is_file() or path.read_bytes() != raw:
            raise ValueError(f"Target artifact byte drift: {name}")
    return {name: sha256_bytes(raw) for name, raw in artifacts.items()}


def main() -> int:
    parser = argparse.ArgumentParser(description="Provider-free Dryad target preparation and verification only.")
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("prepare", "verify"):
        command = commands.add_parser(name)
        command.add_argument("--ratings-path", required=True, type=Path)
        command.add_argument("--freeze-root", required=True, type=Path)
        command.add_argument("--output-root", required=True, type=Path)
    args = parser.parse_args()
    action = prepare if args.command == "prepare" else verify
    print(json.dumps(action(args.ratings_path, args.freeze_root, args.output_root), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
