"""Conditional story bootstrap for the immutable Dryad fixed-half aggregate."""
from __future__ import annotations

import argparse
import ast
from collections import defaultdict
from fractions import Fraction
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import random

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
PARENT = HERE.parent / "hbq-human-alignment-dryad-human-agreement-v1"
PROJECTOR = HERE.parent / "hbq-matched-hanna-20261004/prepare.py"
PROJECTOR_SHA = "2d82e4959c3296ccaa6e6521adb46f85588427d429a544b36a2891ebaea8c7b0"
PROFILE_SHA = "58b4963ca940bb5a949bef7b5c2889bbf9c5e4a032ee721ab521a9e13568f9de"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode()


def checked(path, expected):
    raw = path.read_bytes()
    require(sha(raw) == expected, "Pinned input differs: " + path.name)
    return raw


def parent_module(profile):
    checked(PARENT / "source.py", profile["parent_source_sha256"])
    spec = importlib.util.spec_from_file_location("dryad_fixed_half_parent", PARENT / "source.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def metadata_projector():
    # Extract only the existing pure lexical reader, never run its preparer.
    tree = ast.parse(checked(PROJECTOR, PROJECTOR_SHA))
    functions = [node for node in tree.body if isinstance(node, ast.FunctionDef)
                 and node.name in {"require", "project_json"}]
    require(len(functions) == 2, "Lexical projection source differs")
    namespace = {"json": json}
    exec(compile(ast.Module(body=functions, type_ignores=[]), str(PROJECTOR), "exec"), namespace)
    return namespace["project_json"]


def split_metadata(raw, counts):
    project = metadata_projector()
    mapping = {}
    observed = defaultdict(int)
    for line in raw.splitlines():
        record = project(line, {"source_story_id": True, "partition": True})
        story, partition = record["source_story_id"], record["partition"]
        require(isinstance(story, str) and story not in mapping and
                partition in {"TRAIN", "DEV", "CONFIRMATION"}, "Split identity differs")
        mapping[story] = partition
        observed[partition] += 1
    require(dict(observed) == {**counts, "CONFIRMATION": 57}, "Split counts differ")
    return mapping


def csv_spans(raw):
    """Strict comma/quote lexer. Yield byte spans without decoding field values."""
    i, size = 0, len(raw)
    while i < size:
        fields = []
        while True:
            start = i
            quoted = i < size and raw[i] == 34
            if quoted:
                i += 1
                while True:
                    require(i < size, "Unclosed CSV quote")
                    if raw[i] == 34:
                        if i + 1 < size and raw[i + 1] == 34:
                            i += 2
                            continue
                        i += 1
                        break
                    i += 1
                require(i == size or raw[i] in (44, 10, 13), "CSV quote suffix differs")
            else:
                while i < size and raw[i] not in (44, 10, 13):
                    require(raw[i] != 34, "Unexpected unquoted CSV quote")
                    i += 1
            fields.append((start, i, quoted))
            if i == size:
                yield fields
                return
            delimiter = raw[i]
            i += 1
            if delimiter == 44:
                continue
            if delimiter == 13 and i < size and raw[i] == 10:
                i += 1
            yield fields
            break


def decode_field(raw, span):
    start, end, quoted = span
    value = raw[start:end]
    if quoted:
        value = value[1:-1].replace(b'""', b'"')
    return value.decode("utf-8")


def measurements(raw, mapping, contract, parent):
    axes = contract["measurement"]["axes"]
    iterator = iter(csv_spans(raw))
    header = [decode_field(raw, span) for span in next(iterator)]
    require(len(header) == len(set(header)) and set(header) == {
        "evaluator_index", "story_slot", "story_id", "condition", "topic", "story_text", *axes
    }, "Audited CSV schema differs")
    positions = {name: index for index, name in enumerate(header)}
    pending, evaluator_ids = [], set()
    counts = {"open_rows": 0, "confirmation_rows_metadata_only": 0,
              "rating_fields_decoded": 0, "story_text_fields_decoded": 0,
              "confirmation_rating_fields_decoded": 0}
    for spans in iterator:
        require(len(spans) == len(header), "CSV field count differs")
        story = decode_field(raw, spans[positions["story_id"]])
        evaluator = decode_field(raw, spans[positions["evaluator_index"]])
        require(story in mapping, "Unknown story identity")
        evaluator_ids.add(evaluator)
        partition = mapping[story]
        if partition == "CONFIRMATION":
            counts["confirmation_rows_metadata_only"] += 1
            continue
        values = [int(decode_field(raw, spans[positions[axis]])) for axis in axes]
        require(all(1 <= value <= 9 for value in values), "Open rating range differs")
        pending.append((partition, story, evaluator, values))
        counts["open_rows"] += 1
        counts["rating_fields_decoded"] += len(axes)
    halves = parent.evaluator_halves(evaluator_ids, contract["evaluator_split"]["seed"])
    records = {partition: defaultdict(lambda: {
        "A": {axis: [] for axis in axes}, "B": {axis: [] for axis in axes}
    }) for partition in parent.PARTITIONS}
    for partition, story, evaluator, values in pending:
        for axis, value in zip(axes, values, strict=True):
            records[partition][story][halves[evaluator]][axis].append(value)
    require(all(len(records[p]) == contract["partitions"]["open"][p]
                for p in parent.PARTITIONS), "Open story counts differ")
    counts["global_evaluators"] = len(evaluator_ids)
    return records, counts


def tie_groups(values):
    groups = defaultdict(list)
    for index, value in enumerate(values):
        groups[value].append(index)
    return [groups[value] for value in sorted(groups)]


def weighted_spearman(left_groups, right_groups, weights):
    """Exactly duplicated-sample tie ranks, represented by integer multiplicities."""
    size = sum(weights)
    if size < 2:
        return None
    rank_vectors = []
    for groups in (left_groups, right_groups):
        ranks, before = [0] * len(weights), 0
        for group in groups:
            count = sum(weights[index] for index in group)
            rank = 2 * before + count + 1  # doubled average rank, exact integer
            for index in group:
                ranks[index] = rank
            before += count
        rank_vectors.append(ranks)
    left, right = rank_vectors
    mean = size + 1  # doubled ranks have exactly this mean
    numerator = sum(w * (x - mean) * (y - mean)
                    for w, x, y in zip(weights, left, right, strict=True))
    lss = sum(w * (x - mean) ** 2 for w, x in zip(weights, left, strict=True))
    rss = sum(w * (y - mean) ** 2 for w, y in zip(weights, right, strict=True))
    return numerator / math.sqrt(lss * rss) if lss and rss else None


def percentile(values, probability):
    ordered = sorted(values)
    location = (len(ordered) - 1) * probability
    lower = math.floor(location)
    upper = math.ceil(location)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (location - lower)


def bootstrap_rows(records, axes, minimum, profile, points):
    output = []
    distributions = {}
    for partition in ("TRAIN", "DEV"):
        eligible_sets = [{story for story, halves in records[partition].items()
                          if len(halves["A"][axis]) >= minimum and len(halves["B"][axis]) >= minimum}
                         for axis in axes]
        require(all(ids == eligible_sets[0] for ids in eligible_sets),
                "Axis membership differs; joint bootstrap unavailable")
        stories = sorted(eligible_sets[0])
        require(len(stories) >= 2, "Insufficient eligible stories")
        groups = []
        for axis in axes:
            vectors = []
            for half in ("A", "B"):
                vectors.append([Fraction(sum(records[partition][story][half][axis]),
                                         len(records[partition][story][half][axis])) for story in stories])
            groups.append((tie_groups(vectors[0]), tie_groups(vectors[1])))
        seed = int.from_bytes(hashlib.sha256((profile["seed"] + "\0" + partition).encode()).digest(), "big")
        rng = random.Random(seed)
        samples = [[] for _ in axes]
        for _ in range(profile["draws_per_partition"]):
            weights = [0] * len(stories)
            for _ in stories:
                weights[rng.randrange(len(stories))] += 1
            for sample, (left, right) in zip(samples, groups, strict=True):
                sample.append(weighted_spearman(left, right, weights))
        for axis, sample in zip(axes, samples, strict=True):
            point = next(row for row in points if row["partition"] == partition and row["axis"] == axis)
            defined = [value for value in sample if value is not None]
            undefined = len(sample) - len(defined)
            interval = [percentile(defined, .025), percentile(defined, .975)] if not undefined else None
            output.append({**point, "bootstrap_defined": len(defined), "bootstrap_undefined": undefined,
                           "conditional_percentile_95": interval,
                           "bootstrap_distribution_sha256": sha(canonical(sample))})
            distributions[partition + "/" + axis] = sample
    return output, distributions


def run(ratings_path, split_path):
    profile = json.loads(checked(HERE / "profile.json", PROFILE_SHA))
    parent = parent_module(profile)
    contract = json.loads(checked(PARENT / "protocol-contract.json", profile["parent_contract_sha256"]))
    published = json.loads(checked(PARENT / "result.json", profile["parent_result_sha256"]))
    ratings = checked(ratings_path, profile["ratings_sha256"])
    split = checked(split_path, profile["split_manifest_sha256"])
    mapping = split_metadata(split, contract["partitions"]["open"])
    records, accounting = measurements(ratings, mapping, contract, parent)
    axes = contract["measurement"]["axes"]
    minimum = contract["measurement"]["minimum_ratings_per_story_per_half"]
    points = parent.agreement_rows(records, axes, minimum)
    require(points == published["results"] and len(points) == 24,
            "Exact parent 24-point replay failed; bootstrap prohibited")
    rows, distributions = bootstrap_rows(records, axes, minimum, profile["bootstrap"], points)
    result = {"schema_version": 1, "evidence_class": profile["policy"],
              "profile_sha256": PROFILE_SHA, "source_sha256": sha(Path(__file__).read_bytes()),
              "lexical_projector_sha256": PROJECTOR_SHA,
              "parent_source_sha256": profile["parent_source_sha256"],
              "parent_contract_sha256": profile["parent_contract_sha256"],
              "parent_result_sha256": profile["parent_result_sha256"],
              "input_sha256": {"ratings": profile["ratings_sha256"], "split": profile["split_manifest_sha256"]},
              "exact_parent_points_replayed": True, "evaluator_split": contract["evaluator_split"],
              "field_accounting": accounting, "bootstrap": profile["bootstrap"],
              "interpretation": profile["interpretation"], "results": rows,
              "non_claims": {"provider_calls": False, "new_human_votes": False, "human_ceiling": False,
                             "model_alignment": False, "confirmation_outcomes": False, "promotion": False}}
    return result, distributions


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ratings", required=True, type=Path)
    parser.add_argument("--split-manifest", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    output = args.output.resolve()
    require(not output.exists() and not output.is_relative_to(REPO) and
            not args.ratings.resolve().is_relative_to(output) and
            not args.split_manifest.resolve().is_relative_to(output), "Fresh private output required")
    result, distributions = run(args.ratings, args.split_manifest)
    output.mkdir()
    for name, value in (("result.json", result), ("distributions.json", distributions)):
        with (output / name).open("xb") as stream:
            stream.write(canonical(value))
    print(json.dumps({"result_sha256": sha(canonical(result)), "rows": len(result["results"]),
                      "exact_parent_points_replayed": True, "field_accounting": result["field_accounting"]}))


if __name__ == "__main__":
    main()
