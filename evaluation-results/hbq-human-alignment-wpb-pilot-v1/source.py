"""Provider-free immutable source freeze for the WritingPreferenceBench pilot."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import subprocess
from collections import defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

STUDY_ID = "hbq-human-alignment-wpb-pilot-v1"
SELECTION_SEED = "wpb-pilot-v1-preference-blind-row-components-20260904"
SPLIT_SEED = "wpb-pilot-v1-category-partitions-20260904"
SOURCE_COMMIT = "c6ac5821582e77fb34d27f6b54aac937904ee112"
README_SHA256 = "529c50e79d43dd637d4210c3362d66aeeb8a32220ce460ed852f6a1ef3d74fa3"
ENGLISH_JSON_SHA256 = "c80907b42f83673f026280b3af6cc998b69db4045081745b994f1c20c11a8bdd"
EXPECTED_ROWS = 1200
EXPECTED_CATEGORIES = 51
PARTITION_COUNTS = {"train": 35, "dev": 8, "confirmation": 8}
RESPONSE_FIELDS = frozenset(
    {"response", "score", "model", "completion_tokens", "prompt_tokens", "word_len"}
)


def canonical_json(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode()


def sha256(value: bytes | str | Any) -> str:
    if isinstance(value, bytes):
        payload = value
    elif isinstance(value, str):
        payload = value.encode("utf-8")
    else:
        payload = canonical_json(value)
    return hashlib.sha256(payload).hexdigest()


def _write_json(path: Path, value: Any) -> str:
    payload = canonical_json(value) + b"\n"
    with path.open("xb") as handle:
        handle.write(payload)
    return sha256(payload)


def _read_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


class _UnionFind:
    def __init__(self, count: int) -> None:
        self.parents = list(range(count))

    def find(self, value: int) -> int:
        while self.parents[value] != value:
            self.parents[value] = self.parents[self.parents[value]]
            value = self.parents[value]
        return value

    def union(self, left: int, right: int) -> None:
        left_root, right_root = self.find(left), self.find(right)
        if left_root != right_root:
            self.parents[max(left_root, right_root)] = min(left_root, right_root)


def _require_string(value: Any, field: str, index: int) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"row {index} has an invalid {field}")
    return value


def _validate_response(value: Any, side: str, index: int) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != RESPONSE_FIELDS:
        raise ValueError(f"row {index} has an invalid {side} schema")
    _require_string(value.get("response"), f"{side}.response", index)
    if not isinstance(value.get("score"), int) or not 0 <= value["score"] <= 3:
        raise ValueError(f"row {index} has an invalid {side}.score")
    _require_string(value.get("model"), f"{side}.model", index)
    for name in ("completion_tokens", "prompt_tokens", "word_len"):
        if not isinstance(value.get(name), int) or value[name] < 0:
            raise ValueError(f"row {index} has an invalid {side}.{name}")
    return value


def load_source(source_root: Path) -> tuple[list[Mapping[str, Any]], dict[str, str]]:
    source_root = source_root.resolve()
    source_json = source_root / "WP_bench_english.json"
    source_readme = source_root / "README.md"
    if sha256(source_json.read_bytes()) != ENGLISH_JSON_SHA256:
        raise ValueError("WPB English JSON hash does not match the pinned source")
    if sha256(source_readme.read_bytes()) != README_SHA256:
        raise ValueError("WPB README hash does not match the pinned source")
    completed = subprocess.run(
        ["git", "-C", str(source_root), "rev-parse", "HEAD"],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode or completed.stdout.strip() != SOURCE_COMMIT:
        raise ValueError("WPB source checkout does not match the pinned commit")
    rows = _read_json(source_json)
    if not isinstance(rows, list) or len(rows) != EXPECTED_ROWS:
        raise ValueError("WPB English source must contain exactly 1,200 rows")
    tags: set[str] = set()
    for index, row in enumerate(rows):
        if not isinstance(row, Mapping) or set(row) != {
            "prompt", "prompt_id", "tag", "chosen", "rejected"
        }:
            raise ValueError(f"row {index} has an invalid top-level schema")
        for field in ("prompt", "prompt_id", "tag"):
            _require_string(row.get(field), field, index)
        _validate_response(row["chosen"], "chosen", index)
        _validate_response(row["rejected"], "rejected", index)
        if row["chosen"]["response"] == row["rejected"]["response"]:
            raise ValueError(f"row {index} has identical response texts")
        tags.add(row["tag"])
    if len(tags) != EXPECTED_CATEGORIES:
        raise ValueError("WPB English source must contain exactly 51 categories")
    return rows, {
        "commit": SOURCE_COMMIT,
        "readme_sha256": README_SHA256,
        "english_json_sha256": ENGLISH_JSON_SHA256,
    }


def _row_evidence(index: int, row: Mapping[str, Any]) -> dict[str, Any]:
    response_hashes = sorted(
        (sha256(row["chosen"]["response"]), sha256(row["rejected"]["response"]))
    )
    preference_blind = {
        "seed": SELECTION_SEED,
        "prompt_id": row["prompt_id"],
        "prompt_sha256": sha256(row["prompt"]),
        "response_sha256s": response_hashes,
    }
    return {
        "source_index": index,
        "row_id": f"wpb-en-{index:04d}",
        "row_sha256": sha256(row),
        "category": row["tag"],
        "prompt_id_sha256": sha256(row["prompt_id"]),
        "prompt_sha256": sha256(row["prompt"]),
        "response_sha256s": response_hashes,
        "selection_key_sha256": sha256(preference_blind),
    }


def _components(rows: Sequence[Mapping[str, Any]]) -> dict[int, tuple[int, ...]]:
    union_find = _UnionFind(len(rows))
    first_seen: dict[tuple[str, str], int] = {}
    for index, row in enumerate(rows):
        identifiers = (
            ("prompt_id", row["prompt_id"]),
            ("prompt", sha256(row["prompt"])),
            ("response", sha256(row["chosen"]["response"])),
            ("response", sha256(row["rejected"]["response"])),
        )
        for identifier in identifiers:
            previous = first_seen.setdefault(identifier, index)
            union_find.union(index, previous)
    groups: dict[int, list[int]] = defaultdict(list)
    for index in range(len(rows)):
        groups[union_find.find(index)].append(index)
    return {root: tuple(indices) for root, indices in groups.items()}


def _partition_categories(categories: Sequence[str]) -> dict[str, str]:
    ordered = sorted(categories, key=lambda tag: (sha256(f"{SPLIT_SEED}\0{tag}"), tag))
    train_stop = PARTITION_COUNTS["train"]
    dev_stop = train_stop + PARTITION_COUNTS["dev"]
    partitions: dict[str, str] = {}
    for index, category in enumerate(ordered):
        partitions[category] = (
            "train" if index < train_stop else "dev" if index < dev_stop else "confirmation"
        )
    if {name: list(partitions.values()).count(name) for name in PARTITION_COUNTS} != PARTITION_COUNTS:
        raise AssertionError("deterministic category partition geometry drifted")
    return partitions


def _make_payload(prompt: str, response_a: str, response_b: str) -> bytes:
    return (
        "Evaluate the two responses to the writing request for overall creative-writing quality. "
        "Choose the stronger response; use TIE only if they are genuinely tied.\n\n"
        f"Writing request:\n{prompt}\n\n"
        f"Response A:\n{response_a}\n\n"
        f"Response B:\n{response_b}\n\n"
        "Reply with exactly one token: A, B, or TIE."
    ).encode()


def _selected_rows(rows: Sequence[Mapping[str, Any]]) -> tuple[
    list[dict[str, Any]], list[dict[str, Any]], dict[str, tuple[int, ...]]
]:
    evidence = [_row_evidence(index, row) for index, row in enumerate(rows)]
    components = _components(rows)
    component_by_row = {
        index: indices for indices in components.values() for index in indices
    }
    component_sha_by_row = {
        index: sha256([evidence[item]["row_sha256"] for item in indices])
        for indices in components.values()
        for index in indices
    }
    categories_by_component = {
        indices: sorted({rows[index]["tag"] for index in indices}) for indices in components.values()
    }
    excluded: list[dict[str, Any]] = []
    eligible: dict[str, list[int]] = defaultdict(list)
    for index, row in enumerate(rows):
        indices = component_by_row[index]
        component_categories = categories_by_component[indices]
        if len(component_categories) != 1:
            excluded.append(
                {
                    **evidence[index],
                    "reason": "cross_category_component",
                    "component_sha256": component_sha_by_row[index],
                    "component_categories": component_categories,
                }
            )
        else:
            eligible[row["tag"]].append(index)
    selected_indices: set[int] = set()
    for category, candidates in eligible.items():
        seen_components: set[str] = set()
        for index in sorted(candidates, key=lambda item: (evidence[item]["selection_key_sha256"], item)):
            component_sha = component_sha_by_row[index]
            if component_sha not in seen_components:
                selected_indices.add(index)
                seen_components.add(component_sha)
            if len(seen_components) == 3:
                break
        if len(seen_components) != 3:
            raise ValueError(f"category {category!r} cannot supply three distinct eligible components")
    selected: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        if index in selected_indices:
            selected.append({**evidence[index], "component_sha256": component_sha_by_row[index]})
        elif not any(item["source_index"] == index for item in excluded):
            excluded.append(
                {
                    **evidence[index],
                    "reason": "category_cap_or_component_duplicate",
                    "component_sha256": component_sha_by_row[index],
                }
            )
    if len(selected) != EXPECTED_CATEGORIES * 3:
        raise AssertionError("selection did not retain exactly three rows per category")
    if len(excluded) + len(selected) != len(rows):
        raise AssertionError("selection accounting is incomplete")
    return selected, sorted(excluded, key=lambda item: item["source_index"]), components


def freeze(source_root: Path | str, output_root: Path | str) -> dict[str, Any]:
    """Create an immutable local descendant; it never contacts a provider."""
    source_root, output_root = Path(source_root), Path(output_root)
    if output_root.exists():
        raise FileExistsError("output root already exists; immutable freeze outputs are never reused")
    rows, source = load_source(source_root)
    selected, excluded, components = _selected_rows(rows)
    partitions = _partition_categories(sorted({row["tag"] for row in rows}))
    for item in selected:
        item["partition"] = partitions[item["category"]]
    by_category: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in selected:
        by_category[item["category"]].append(item)
    if any(len(items) != 3 for items in by_category.values()):
        raise AssertionError("a category does not have exactly three selected rows")
    output_root.mkdir(parents=True)
    program_sha = sha256(Path(__file__).read_bytes())
    source_inventory = [
        {"source_index": index, "row_id": f"wpb-en-{index:04d}", "row_sha256": sha256(row)}
        for index, row in enumerate(rows)
    ]
    component_inventory = [
        {
            "component_sha256": sha256(
                [source_inventory[index]["row_sha256"] for index in indices]
            ),
            "source_indices": list(indices),
            "categories": sorted({rows[index]["tag"] for index in indices}),
        }
        for _, indices in sorted(components.items())
    ]
    provenance = {
        "format_version": 1,
        "study_id": STUDY_ID,
        "kind": "provider_free_immutable_source_freeze",
        "source": {**source, "row_count": EXPECTED_ROWS, "category_count": EXPECTED_CATEGORIES, "license": "ODC-BY; see pinned upstream README"},
        "source_program_sha256": program_sha,
        "selection": {
            "selection_seed": SELECTION_SEED,
            "split_seed": SPLIT_SEED,
            "rule": "preference-blind hash ordering, three rows per category from distinct non-cross-category components",
            "selected_count": len(selected),
            "excluded_count": len(excluded),
            "excluded_cross_category_count": sum(item["reason"] == "cross_category_component" for item in excluded),
        },
        "source_row_hashes": source_inventory,
        "component_inventory": component_inventory,
        "selected": selected,
        "excluded": excluded,
    }
    _write_json(output_root / "provenance-selection-manifest.json", provenance)
    split_manifest = {
        "format_version": 1,
        "study_id": STUDY_ID,
        "source_manifest_sha256": sha256(canonical_json(provenance) + b"\n"),
        "rule": "whole categories assigned by deterministic category hash; no labels, scores, or model outputs participate",
        "partitions": [
            {"category": category, "partition": partitions[category], "category_hash": sha256(f"{SPLIT_SEED}\0{category}")}
            for category in sorted(partitions)
        ],
        "counts": {name: list(partitions.values()).count(name) for name in PARTITION_COUNTS},
    }
    _write_json(output_root / "split-manifest.json", split_manifest)
    execution_cells: list[dict[str, Any]] = []
    targets: list[dict[str, Any]] = []
    for selected_item in sorted(selected, key=lambda item: item["row_id"]):
        row = rows[selected_item["source_index"]]
        responses = sorted(
            ((sha256(row["chosen"]["response"]), row["chosen"]["response"]), (sha256(row["rejected"]["response"]), row["rejected"]["response"]))
        )
        response_a_hash, response_a = responses[0]
        response_b_hash, response_b = responses[1]
        payload = _make_payload(row["prompt"], response_a, response_b)
        cell_id = "wpb-pair-" + selected_item["row_id"]
        execution_cells.append(
            {
                "cell_id": cell_id,
                "partition": selected_item["partition"],
                "prompt": row["prompt"],
                "prompt_sha256": selected_item["prompt_sha256"],
                "response_a": response_a,
                "response_a_sha256": response_a_hash,
                "response_b": response_b,
                "response_b_sha256": response_b_hash,
                "payload_utf8_base64": base64.b64encode(payload).decode("ascii"),
                "payload_sha256": sha256(payload),
            }
        )
        targets.append(
            {
                "cell_id": cell_id,
                "partition": selected_item["partition"],
                "category": selected_item["category"],
                "source_row_sha256": selected_item["row_sha256"],
                "preferred_side": "A" if response_a_hash == sha256(row["chosen"]["response"]) else "B",
                "chosen_score": row["chosen"]["score"],
                "rejected_score": row["rejected"]["score"],
            }
        )
    execution_inputs = {
        "format_version": 1,
        "study_id": STUDY_ID,
        "endpoint_neutral": True,
        "preference_labels_or_scores_present": False,
        "response_assignment": "A/B is ascending exact UTF-8 response SHA-256, never chosen/rejected order",
        "cells": execution_cells,
    }
    _write_json(output_root / "execution-inputs.json", execution_inputs)
    _write_json(
        output_root / "local-targets.json",
        {
            "format_version": 1,
            "study_id": STUDY_ID,
            "local_only": True,
            "not_for_provider_disclosure": True,
            "targets": targets,
        },
    )
    default_cells = [cell for cell in execution_cells if cell["partition"] != "confirmation"]
    default_schedule = {
        "format_version": 1,
        "study_id": STUDY_ID,
        "kind": "default_executable_schedule",
        "confirmation_excluded": True,
        "open_partitions": ["train", "dev"],
        "cells": [
            {key: cell[key] for key in ("cell_id", "partition", "payload_sha256")}
            for cell in default_cells
        ],
    }
    _write_json(output_root / "default-schedule.json", default_schedule)
    return {
        "study_id": STUDY_ID,
        "source_rows": len(rows),
        "categories": len(by_category),
        "components": len(components),
        "selected": len(selected),
        "excluded": len(excluded),
        "cross_category_excluded": sum(item["reason"] == "cross_category_component" for item in excluded),
        "default_schedule_cells": len(default_cells),
        "confirmation_cells": len(execution_cells) - len(default_cells),
        "output_root": str(output_root.resolve()),
    }


def load_default_schedule(output_root: Path | str) -> Mapping[str, Any]:
    """Rebuild and verify the only executable schedule: exact TRAIN plus DEV cells."""
    output_root = Path(output_root)
    input_path = output_root / "execution-inputs.json"
    schedule_path = output_root / "default-schedule.json"
    try:
        input_bytes, schedule_bytes = input_path.read_bytes(), schedule_path.read_bytes()
        inputs, schedule = json.loads(input_bytes), json.loads(schedule_bytes)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("default schedule or execution inputs are unreadable") from error
    if (
        not isinstance(inputs, Mapping)
        or not isinstance(schedule, Mapping)
        or input_bytes != canonical_json(inputs) + b"\n"
        or schedule_bytes != canonical_json(schedule) + b"\n"
    ):
        raise ValueError("default schedule and execution inputs must be exact canonical JSON")
    if (
        inputs.get("format_version") != 1
        or inputs.get("study_id") != STUDY_ID
        or inputs.get("endpoint_neutral") is not True
        or inputs.get("preference_labels_or_scores_present") is not False
        or inputs.get("response_assignment")
        != "A/B is ascending exact UTF-8 response SHA-256, never chosen/rejected order"
        or set(inputs)
        != {
            "format_version",
            "study_id",
            "endpoint_neutral",
            "preference_labels_or_scores_present",
            "response_assignment",
            "cells",
        }
        or not isinstance(inputs.get("cells"), list)
    ):
        raise ValueError("execution inputs have an invalid immutable identity")
    expected_cells: list[dict[str, str]] = []
    for cell in inputs["cells"]:
        if not isinstance(cell, Mapping) or set(cell) != {
            "cell_id",
            "partition",
            "prompt",
            "prompt_sha256",
            "response_a",
            "response_a_sha256",
            "response_b",
            "response_b_sha256",
            "payload_utf8_base64",
            "payload_sha256",
        }:
            raise ValueError("execution inputs contain an invalid cell")
        cell_id, partition, payload_sha256, prompt, response_a, response_b = (
            cell.get("cell_id"),
            cell.get("partition"),
            cell.get("payload_sha256"),
            cell.get("prompt"),
            cell.get("response_a"),
            cell.get("response_b"),
        )
        if (
            not isinstance(cell_id, str)
            or not isinstance(partition, str)
            or not isinstance(payload_sha256, str)
            or not isinstance(prompt, str)
            or not isinstance(response_a, str)
            or not isinstance(response_b, str)
            or not all(
                isinstance(cell.get(name), str)
                for name in (
                    "prompt_sha256",
                    "response_a_sha256",
                    "response_b_sha256",
                    "payload_utf8_base64",
                )
            )
            or cell.get("prompt_sha256") != sha256(prompt)
            or cell.get("response_a_sha256") != sha256(response_a)
            or cell.get("response_b_sha256") != sha256(response_b)
            or cell["response_a_sha256"] >= cell["response_b_sha256"]
        ):
            raise ValueError("execution inputs contain an invalid cell summary")
        try:
            payload = base64.b64decode(cell["payload_utf8_base64"], validate=True)
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError("execution inputs contain an invalid payload encoding") from error
        if payload_sha256 != sha256(payload) or payload != _make_payload(prompt, response_a, response_b):
            raise ValueError("execution inputs contain a payload that does not bind its cell")
        if partition in {"train", "dev"}:
            expected_cells.append(
                {"cell_id": cell_id, "partition": partition, "payload_sha256": payload_sha256}
            )
        elif partition != "confirmation":
            raise ValueError("execution inputs contain an unknown partition")
    expected = {
        "format_version": 1,
        "study_id": STUDY_ID,
        "kind": "default_executable_schedule",
        "confirmation_excluded": True,
        "open_partitions": ["train", "dev"],
        "cells": expected_cells,
    }
    if len(expected_cells) != 129 or len({cell["cell_id"] for cell in expected_cells}) != 129:
        raise ValueError("default schedule geometry is incomplete or has duplicate cells")
    if schedule != expected:
        raise ValueError("default schedule differs from its canonical execution-input reconstruction")
    return schedule


def _main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    arguments = parser.parse_args()
    print(json.dumps(freeze(arguments.source_root, arguments.output_root), sort_keys=True))


if __name__ == "__main__":
    _main()
