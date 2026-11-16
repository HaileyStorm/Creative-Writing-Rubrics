"""Recompute retained post-result Dryad evaluator-half sensitivity aggregates."""
from __future__ import annotations

import argparse
from fractions import Fraction
import hashlib
import importlib.util
import json
from pathlib import Path
from statistics import median

HERE = Path(__file__).resolve().parent
PARENT = HERE.parent / "hbq-human-alignment-dryad-human-agreement-v1"
PARENT_SHA = "de21884862ac28dbeba840b28aede1ba38ab9245f9557b11a47ad93d22e730fd"
AXES_SHA = "753c8f17eed517cff874a5f0778b3ea58a7a28698802e6a12a7d325c692676d5"
INDICES_SHA = "902c83e7149c8a39766892a5b4b602c0bdf4fec0e15dc24ddfb3cf3a7b92e5fa"
COMPONENTS = {"novelty": ("novel", "original", "rare"),
              "usefulness": ("appropriate", "feasible", "publishable")}


def checked(path, expected):
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected:
        raise ValueError("Pinned file differs: " + path.name)
    return raw


def compare(actual, expected):
    if isinstance(expected, float):
        if actual is None or abs(actual - expected) > 1e-12:
            raise ValueError("Aggregate value differs")
    elif actual != expected:
        raise ValueError("Aggregate value differs")


def run(ratings, manifest):
    checked(PARENT / "source.py", PARENT_SHA)
    axes_reference = json.loads(checked(HERE / "axes.json", AXES_SHA))
    indices_reference = json.loads(checked(HERE / "indices.json", INDICES_SHA))
    spec = importlib.util.spec_from_file_location("dryad_parent", PARENT / "source.py")
    parent = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(parent)
    contract = parent.load_contract()
    for path, key in ((ratings, "v2_sha256"), (manifest, "split_manifest_sha256")):
        if parent.sha256_file(path) != contract["sources"][key]:
            raise ValueError("Pinned private input differs")
    axes = contract["measurement"]["axes"]
    counts = contract["partitions"]["open"]
    split = parent.load_split_manifest(manifest, counts)
    seeds = [contract["evaluator_split"]["seed"], *axes_reference["seeds"]]
    if seeds[1:] != [f"dryad-alternate-evaluator-halves-20261113-{i:02d}" for i in range(20)]:
        raise ValueError("Alternate split schedule differs")
    series, sizes, composite_series, composite_sizes = {}, {}, {}, {}
    for seed_number, seed in enumerate(seeds):
        records = parent.collect_open_measurements(ratings, split, axes, counts, seed)
        rows = parent.agreement_rows(records, axes, contract["measurement"]["minimum_ratings_per_story_per_half"])
        if seed_number == 0:
            original = json.loads((PARENT / "result.json").read_text(encoding="utf-8"))["results"]
            if rows != original:
                raise ValueError("Published original split does not replay")
        for row in rows:
            key = (row["partition"], row["axis"])
            series.setdefault(key, []).append(row["spearman_average_ties"])
            sizes.setdefault(key, []).append(row["eligible_stories"])
        for partition in parent.PARTITIONS:
            for name, components in COMPONENTS.items():
                vectors = [[], []]
                for halves in records[partition].values():
                    component_counts = [{len(halves[side][axis]) for axis in components} for side in ("A", "B")]
                    if any(len(group) != 1 for group in component_counts):
                        raise ValueError("Composite component coverage differs")
                    ns = [next(iter(group)) for group in component_counts]
                    if min(ns) < contract["measurement"]["minimum_ratings_per_story_per_half"]:
                        continue
                    for index, side in enumerate(("A", "B")):
                        vectors[index].append(Fraction(sum(sum(halves[side][axis]) for axis in components), 3 * ns[index]))
                key = (partition, name)
                value = parent.spearman_average_ties(*vectors)
                if value is None:
                    raise ValueError("Undefined composite agreement")
                composite_series.setdefault(key, []).append(value)
                composite_sizes.setdefault(key, []).append(len(vectors[0]))
    for row in axes_reference["rows"]:
        key = (row["partition"], row["axis"])
        values, ns = series[key], sizes[key]
        for field, value in {"original": values[0], "defined": len(values[1:]), "min": min(values[1:]),
                             "median": median(values[1:]), "max": max(values[1:]),
                             "eligible_min": min(ns[1:]), "eligible_max": max(ns[1:])}.items():
            compare(value, row[field])
    for row in indices_reference["rows"]:
        key = (row["partition"], row["index"])
        values, ns = composite_series[key], composite_sizes[key]
        for field, value in {"original_split": values[0], "alternate_min": min(values[1:]),
                             "alternate_median": median(values[1:]), "alternate_max": max(values[1:]),
                             "eligible_stories_min": min(ns), "eligible_stories_max": max(ns)}.items():
            compare(value, row[field])
    print("Verified 24 axis and four index summaries across the original and 20 alternate splits.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--ratings", required=True, type=Path)
    parser.add_argument("--split-manifest", required=True, type=Path)
    args = parser.parse_args()
    run(args.ratings, args.split_manifest)
