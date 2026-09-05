"""Portable replay for the published Dryad one-split human-agreement aggregate."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from collections import defaultdict
from fractions import Fraction
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parent
CONTRACT_PATH = ROOT / "protocol-contract.json"
CONTRACT_SHA256 = "4f9b01f93e54c8b5a6f518aea8d7fbbe1e11646f46edd661f51d9d1336b99442"
PARTITIONS = ("TRAIN", "DEV")
CONFIRMATION = "CONFIRMATION"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def average_ranks(values: list[Fraction]) -> list[Fraction]:
    ranks = [Fraction(0) for _ in values]
    ordered = sorted(enumerate(values), key=lambda pair: pair[1])
    start = 0
    while start < len(ordered):
        end = start + 1
        while end < len(ordered) and ordered[end][1] == ordered[start][1]:
            end += 1
        mean_rank = Fraction(start + 1 + end, 2)
        for index, _ in ordered[start:end]:
            ranks[index] = mean_rank
        start = end
    return ranks


def spearman_average_ties(left: list[Fraction], right: list[Fraction]) -> float | None:
    if len(left) != len(right) or len(left) < 2:
        return None
    left_ranks = average_ranks(left)
    right_ranks = average_ranks(right)
    count = Fraction(len(left))
    left_mean = sum(left_ranks, Fraction(0)) / count
    right_mean = sum(right_ranks, Fraction(0)) / count
    numerator = sum((x - left_mean) * (y - right_mean) for x, y in zip(left_ranks, right_ranks, strict=True))
    left_ss = sum((x - left_mean) ** 2 for x in left_ranks)
    right_ss = sum((y - right_mean) ** 2 for y in right_ranks)
    if left_ss == 0 or right_ss == 0:
        return None
    return float(numerator / Fraction.from_float(math.sqrt(float(left_ss * right_ss))))


def load_contract(contract_path: Path = CONTRACT_PATH) -> dict[str, Any]:
    if sha256_file(contract_path) != CONTRACT_SHA256:
        raise ValueError("Published protocol contract hash drift")
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    if contract.get("evidence_class") != "human_internal_agreement_one_fixed_split_only":
        raise ValueError("Protocol contract class drift")
    return contract


def evaluator_halves(evaluator_ids: Iterable[str], seed: str) -> dict[str, str]:
    ids = sorted(set(evaluator_ids), key=lambda value: (hashlib.sha256(f"{seed}\0{value}".encode("utf-8")).hexdigest(), value))
    if len(ids) != 600:
        raise ValueError("Global evaluator inventory drift")
    return {value: "A" if index < 300 else "B" for index, value in enumerate(ids)}


def load_split_manifest(path: Path, expected_counts: dict[str, int]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    counts: dict[str, int] = defaultdict(int)
    with path.open(encoding="utf-8") as stream:
        for line in stream:
            record = json.loads(line)
            story_id, partition = record["source_story_id"], record["partition"]
            if story_id in mapping or partition not in {*PARTITIONS, CONFIRMATION}:
                raise ValueError("Split manifest identity or partition drift")
            mapping[story_id] = partition
            counts[partition] += 1
    if {partition: counts[partition] for partition in PARTITIONS} != expected_counts or counts[CONFIRMATION] != 57:
        raise ValueError("Split manifest partition-count drift")
    return mapping


def collect_open_measurements(
    ratings_path: Path,
    split_by_story: dict[str, str],
    axes: list[str],
    expected_counts: dict[str, int],
    seed: str,
) -> dict[str, dict[str, dict[str, dict[str, list[int]]]]]:
    with ratings_path.open(encoding="utf-8", newline="") as stream:
        reader = csv.reader(stream)
        header = next(reader)
        positions = {name: index for index, name in enumerate(header)}
        if set(positions) != {"evaluator_index", "story_slot", "story_id", "condition", "topic", "story_text", *axes}:
            raise ValueError("Audited v2 schema drift")
        pending: list[tuple[str, str, list[str]]] = []
        evaluator_ids: set[str] = set()
        for row in reader:
            story_id = row[positions["story_id"]]
            partition = split_by_story.get(story_id)
            if partition is None:
                raise ValueError("Unknown v2 story ID during source join")
            evaluator_id = row[positions["evaluator_index"]]
            evaluator_ids.add(evaluator_id)
            if partition == CONFIRMATION:
                continue
            pending.append((partition, story_id, row))
    halves = evaluator_halves(evaluator_ids, seed)
    records: dict[str, dict[str, dict[str, dict[str, list[int]]]]] = {
        partition: defaultdict(lambda: {"A": {axis: [] for axis in axes}, "B": {axis: [] for axis in axes}})
        for partition in PARTITIONS
    }
    for partition, story_id, row in pending:
        values = records[partition][story_id][halves[row[positions["evaluator_index"]]]]
        for axis in axes:
            value = int(row[positions[axis]])
            if not 1 <= value <= 9:
                raise ValueError("Open rating range drift")
            values[axis].append(value)
    if any(len(records[partition]) != expected_counts[partition] for partition in PARTITIONS):
        raise ValueError("Open story cardinality drift")
    return records


def agreement_rows(records: dict[str, Any], axes: list[str], minimum: int) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for partition in PARTITIONS:
        for axis in axes:
            left: list[Fraction] = []
            right: list[Fraction] = []
            excluded = 0
            for halves in records[partition].values():
                a_values, b_values = halves["A"][axis], halves["B"][axis]
                if len(a_values) < minimum or len(b_values) < minimum:
                    excluded += 1
                    continue
                left.append(Fraction(sum(a_values), len(a_values)))
                right.append(Fraction(sum(b_values), len(b_values)))
            output.append({"partition": partition, "axis": axis, "eligible_stories": len(left), "excluded_for_coverage": excluded, "spearman_average_ties": spearman_average_ties(left, right)})
    return output


def run(ratings_path: Path, split_manifest_path: Path) -> dict[str, Any]:
    contract = load_contract()
    sources = contract["sources"]
    if sha256_file(ratings_path) != sources["v2_sha256"] or sha256_file(split_manifest_path) != sources["split_manifest_sha256"]:
        raise ValueError("Pinned source hash drift")
    axes = list(contract["measurement"]["axes"])
    counts = contract["partitions"]["open"]
    split_by_story = load_split_manifest(split_manifest_path, counts)
    records = collect_open_measurements(ratings_path, split_by_story, axes, counts, contract["evaluator_split"]["seed"])
    return {
        "schema_version": 1,
        "evidence_class": contract["evidence_class"],
        "contract_sha256": CONTRACT_SHA256,
        "script_sha256": sha256_file(Path(__file__).resolve()),
        "sources": {"v2_sha256": sources["v2_sha256"], "split_manifest_sha256": sources["split_manifest_sha256"]},
        "historical_parent_reference": contract["historical_parent_reference"],
        "evaluator_split": contract["evaluator_split"],
        "measurement": {
            "minimum_ratings_per_story_per_half": contract["measurement"]["minimum_ratings_per_story_per_half"],
            "statistic": contract["measurement"]["statistic"],
            "uncertainty": "No bootstrap or confidence interval was run; this fixed finite split has unquantified one-split sensitivity.",
        },
        "results": agreement_rows(records, axes, contract["measurement"]["minimum_ratings_per_story_per_half"]),
        "non_claims": contract["non_claims"],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ratings", required=True, type=Path)
    parser.add_argument("--split-manifest", required=True, type=Path)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--output", type=Path)
    mode.add_argument("--check-result", type=Path)
    args = parser.parse_args()
    result = run(args.ratings, args.split_manifest)
    if args.check_result is not None:
        published = json.loads(args.check_result.read_text(encoding="utf-8"))
        if published != result:
            raise ValueError("Published aggregate does not match the pinned portable replay")
        return 0
    with args.output.open("xb") as stream:
        stream.write(canonical_json_bytes(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
