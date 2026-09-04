"""Frozen TRAIN-only replication of V16's direct/comparative measurement."""
from __future__ import annotations

import base64
import csv
import hashlib
import importlib.util
import io
import json
import subprocess
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from functools import cache
from pathlib import Path
from types import ModuleType
from typing import Any

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
STUDY_ID = "hbq-human-alignment-optimizer-v17-comparative-train-replication-v1"
CONTRACT = HERE / "experiment-contract.json"
V16 = REPO / "evaluation-results/hbq-human-alignment-optimizer-v16-comparative-train-v1/study.py"
V16_SHA256 = "8e24c0e0469339b3ad0a168bfb4aa5d4532c9cfea85a95d72764dc30037c34aa"
V16_COMMIT = "3c1bec6"
V16_CONTRACT = V16.with_name("experiment-contract.json")
V16_CONTRACT_SHA256 = "3d0aaee0e4e37e73d50cbd37969f006ac8b90deeebd74caa9512d323c94d7eb8"
V16_CONTRACT_COMMIT = "bfdb0d2"
DIMS = ("Relevance", "Coherence", "Empathy", "Surprise", "Engagement", "Complexity")
DIRECT, FORWARD, REVERSE = "direct_integer", "comparative_forward", "comparative_reverse"
MAX_CONCURRENCY = 10


def canonical(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")


def sha256(value: bytes | Any) -> str:
    return hashlib.sha256(value if isinstance(value, bytes) else canonical(value)).hexdigest()


def strict(raw: bytes, label: str) -> dict[str, Any]:
    try:
        value = json.loads(raw.decode("utf-8"), parse_constant=lambda token: (_ for _ in ()).throw(ValueError(token)))
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise ValueError(f"invalid {label}") from error
    if not isinstance(value, dict) or canonical(value) != raw:
        raise ValueError(f"invalid {label}")
    return value


def _load_exact(path: Path, digest: str, commit: str, name: str) -> ModuleType:
    raw = Path(path).read_bytes()
    relative = Path(path).relative_to(REPO).as_posix()
    blob = subprocess.run(["git", "-C", str(REPO), "show", f"{commit}:{relative}"], capture_output=True, check=False)
    if blob.returncode or sha256(raw) != digest or blob.stdout != raw:
        raise ValueError("pinned predecessor drifted")
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ValueError("pinned predecessor cannot load")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def contract() -> dict[str, Any]:
    value = strict(CONTRACT.read_bytes(), "V17 experiment contract")
    expected = {
        "analysis_rule": {
            "comparative_primary": "per_story_mean_of_forward_and_reverse_then_within_prompt_average_tie_spearman_then_macro_across_six_dimensions",
            "direct_reuse": "historical_v15_direct_measurements_are_endpoint_separate_and_noncontemporaneous",
            "fixed_three": "rho_undefined",
            "hanna_compatible_dropundefined_with_retained_dropped_count": "per criterion, mean only defined prompt correlations; report retained and dropped prompt IDs and counts; macro undefined only when an entire criterion is undefined",
            "strict_full_five": "coverage guard: macro is undefined whenever any of the five prompt correlations is undefined",
        },
        "authority": {
            "confirmation": "none",
            "development_train_only": True,
            "endpoint_pooling": "forbidden",
            "generalization": "none",
            "promotion": "none",
            "runtime": "none",
            "selection": "none",
        },
        "format_version": 1,
        "geometry": {"comparative_batches": 10, "direct_new": 38, "direct_reused": 12, "groups": 5, "items": 50, "logical_cells": 48, "max_concurrency": 10},
        "kind": "comparative_hanna_train_replication_measurement",
        "study_id": STUDY_ID,
    }
    if value != expected:
        raise ValueError("V17 experiment contract drifted")
    return value


@cache
def _v16() -> ModuleType:
    value = _load_exact(V16, V16_SHA256, V16_COMMIT, "_v17_v16")
    contract_raw = V16_CONTRACT.read_bytes()
    blob = subprocess.run(
        ["git", "-C", str(REPO), "show", f"{V16_CONTRACT_COMMIT}:{V16_CONTRACT.relative_to(REPO).as_posix()}"],
        capture_output=True,
        check=False,
    )
    if blob.returncode or sha256(contract_raw) != V16_CONTRACT_SHA256 or blob.stdout != contract_raw:
        raise ValueError("pinned V16 contract drifted")
    value.contract()
    if value.DIMS != DIMS or (value.DIRECT, value.FORWARD, value.REVERSE) != (DIRECT, FORWARD, REVERSE):
        raise ValueError("V16 protocol constants drifted")
    return value


def _v15() -> ModuleType:
    return _v16()._v15()


def _selection(original: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    counts = Counter(str(row["prompt_group_id"]) for row in original)
    ordered = [group for group, _count in sorted(counts.items(), key=lambda pair: (-pair[1], pair[0]))]
    v16_groups, groups = ordered[:5], ordered[5:10]
    if len(counts) != 24 or [counts[group] for group in v16_groups] != [5, 4, 4, 4, 4] or [counts[group] for group in groups] != [3, 3, 2, 2, 2]:
        raise ValueError("V17 successor group selection drifted")
    return {"groups": groups, "counts": {group: counts[group] for group in groups}, "v16_predecessor_groups": v16_groups}


def _panel(*, split_manifest: Path, hanna_csv: Path, successor_contract: Path) -> tuple[ModuleType, list[dict[str, Any]], dict[str, Any]]:
    v15 = _v15()
    original = v15._train48_items(split_manifest=split_manifest, hanna_csv=hanna_csv, successor_contract=successor_contract)
    selection = _selection(original)
    groups = selection["groups"]
    existing = {(row["prompt"], row["story"]): row for row in original if row["prompt_group_id"] in set(groups)}
    raw = hanna_csv.read_bytes()
    rows = list(csv.DictReader(io.StringIO(raw.decode("utf-8-sig"))))
    expected_columns = {"Story ID", "Prompt", "Human", "Story", "Model", *DIMS, "Worker ID", "Assignment ID", "Work time in seconds", "Name"}
    if not rows or set(rows[0]) != expected_columns:
        raise ValueError("pinned HANNA CSV schema drifted")
    systems: dict[str, dict[tuple[str, str], list[Mapping[str, str]]]] = {group: defaultdict(list) for group in groups}
    for row in rows:
        group = "prompt-" + hashlib.sha256(row["Prompt"].encode("utf-8")).hexdigest()[:16]
        if group in systems and row["Model"] != "Human":
            systems[group][(row["Story ID"], row["Model"])].append(row)
    panel: list[dict[str, Any]] = []
    for group in groups:
        group_systems = systems[group]
        if len(group_systems) != 10 or len({key[0] for key in group_systems}) != 10 or len({key[1] for key in group_systems}) != 10:
            raise ValueError("V17 group lacks ten non-Human original systems")
        for (story_id, model), values in sorted(group_systems.items(), key=lambda pair: (pair[0][1], pair[0][0])):
            if len(values) != 3 or len({row["Prompt"] for row in values}) != 1 or len({row["Story"] for row in values}) != 1:
                raise ValueError("V17 source system annotation geometry drifted")
            prompt, story = values[0]["Prompt"], values[0]["Story"]
            target = {dimension: sum(float(row[dimension]) for row in values) / 3 for dimension in DIMS}
            inherited = existing.get((prompt, story))
            if inherited is None:
                item_id = "item-" + sha256({"prompt_group_id": group, "story_id": story_id, "source_model": model})[:16]
                binding = sha256({"prompt_group_id": group, "story_id": story_id, "model": model, "prompt": prompt, "story": story})
                historical = False
            else:
                item_id, binding, historical = inherited["item_id"], inherited["source_binding_sha256"], True
                if inherited["target"] != target:
                    raise ValueError("V17 reused V15 target drifted")
            panel.append({"item_id": item_id, "prompt_group_id": group, "source_binding_sha256": binding, "target": target, "prompt": prompt, "story": story, "historical_v15_direct": historical})
    if len(panel) != 50 or len({row["item_id"] for row in panel}) != 50 or sum(row["historical_v15_direct"] for row in panel) != 12:
        raise ValueError("V17 panel geometry drifted")
    return v15, sorted(panel, key=lambda row: (row["prompt_group_id"], row["item_id"])), selection


def _batch_payload(*, instruction: str, profile: Mapping[str, Any], prompt: str, ordered: Sequence[Mapping[str, Any]]) -> bytes:
    v16 = _v16()
    if len(ordered) != 10:
        raise ValueError("V17 comparative payload geometry drifted")
    serial = [{"item_id": row["item_id"], "story": row["story"]} for row in ordered]
    value = {
        "format_version": 1,
        "study_id": STUDY_ID,
        "instruction": instruction,
        "profile": dict(profile),
        "writing": {"prompt": prompt, "story": canonical(serial).decode("utf-8")},
        "response_schema": v16._batch_schema(),
    }
    if set(value) != {"format_version", "study_id", "instruction", "profile", "writing", "response_schema"} or set(value["writing"]) != {"prompt", "story"} or "target" in value:
        raise ValueError("V17 comparative payload leaked non-outbound data")
    return canonical(value)


def _direct_template_commitments(v15: ModuleType, v16: ModuleType) -> dict[str, str]:
    instruction, _anchors = v15._shared_anchor_payload()
    profile, schema = v15._condition(DIRECT, v15.ANCHORS)
    candidate = v16._direct_candidate(v15)
    if candidate["instruction_sha256"] != sha256(instruction.encode("utf-8")) or candidate["profile_sha256"] != sha256(profile):
        raise ValueError("V16 direct profile binding drifted")
    return {"instruction_sha256": candidate["instruction_sha256"], "profile_sha256": candidate["profile_sha256"], "response_schema_sha256": sha256(schema)}


def _comparative_template_commitments(v16: ModuleType, v15: ModuleType) -> tuple[dict[str, Any], str, dict[str, Any], dict[str, str]]:
    candidate, instruction, profile = v16._batch_candidate(v15)
    schema = v16._batch_schema()
    if candidate["instruction_sha256"] != sha256(instruction.encode("utf-8")) or candidate["profile_sha256"] != sha256(profile):
        raise ValueError("V16 comparative profile binding drifted")
    return candidate, instruction, profile, {"instruction_sha256": candidate["instruction_sha256"], "profile_sha256": candidate["profile_sha256"], "response_schema_sha256": sha256(schema)}


def schedule(*, split_manifest: Path, hanna_csv: Path, successor_contract: Path) -> dict[str, Any]:
    contract_value = contract()
    v16 = _v16()
    v15, panel, selection = _panel(split_manifest=Path(split_manifest), hanna_csv=Path(hanna_csv), successor_contract=Path(successor_contract))
    v15_schedule = v15.schedule(split_manifest=Path(split_manifest), hanna_csv=Path(hanna_csv), successor_contract=Path(successor_contract))
    direct_rows = {row["item_id"]: row for row in v15_schedule["cells"] if row["condition"] == DIRECT}
    direct_candidate = v16._direct_candidate(v15)
    batch_candidate, batch_instruction, batch_profile, comparative_template = _comparative_template_commitments(v16, v15)
    reused: list[dict[str, Any]] = []
    cells: list[dict[str, Any]] = []
    for row in panel:
        if row["historical_v15_direct"]:
            source = direct_rows.get(row["item_id"])
            if not isinstance(source, Mapping):
                raise ValueError("V17 V15 direct reuse is absent")
            payload = base64.b64decode(source["payload_base64"], validate=True)
            if source.get("payload_sha256") != sha256(payload):
                raise ValueError("V17 exact V15 direct reuse drifted")
            reused.append({
                "cell_id": source["cell_id"], "source_cell_id": source["cell_id"], "condition": DIRECT, **direct_candidate,
                "item_id": row["item_id"], "prompt_group_id": row["prompt_group_id"], "partition": "train",
                "source_binding_sha256": row["source_binding_sha256"], "payload_base64": source["payload_base64"],
                "payload_sha256": source["payload_sha256"], "endpoint_payload_sha256s": source["endpoint_payload_sha256s"],
                "reuse_provenance": {"v15_study_sha256": v16.V15_SHA256, "v15_cell_id": source["cell_id"], "v15_payload_sha256": source["payload_sha256"]},
            })
        else:
            payload = v15._payload(instruction=v15.SHARED_INSTRUCTION, anchors=v15.ANCHORS, condition=DIRECT, item=row)
            digest = sha256(payload)
            cells.append({
                "cell_id": "v17-direct-" + sha256({"item": row["item_id"]})[:20], "condition": DIRECT, **direct_candidate,
                "item_id": row["item_id"], "prompt_group_id": row["prompt_group_id"], "partition": "train",
                "source_binding_sha256": row["source_binding_sha256"], "payload_base64": base64.b64encode(payload).decode("ascii"),
                "payload_sha256": digest, "endpoint_payload_sha256s": {"grok_primary": digest, "sol_later": digest},
            })
    for group in selection["groups"]:
        group_rows = [row for row in panel if row["prompt_group_id"] == group]
        if len(group_rows) != 10 or len({row["prompt"] for row in group_rows}) != 1:
            raise ValueError("V17 comparative group panel drifted")
        forward = sorted(group_rows, key=lambda row: row["item_id"])
        for condition, ordered in ((FORWARD, forward), (REVERSE, list(reversed(forward)))):
            payload = _batch_payload(instruction=batch_instruction, profile=batch_profile, prompt=forward[0]["prompt"], ordered=ordered)
            digest = sha256(payload)
            cells.append({
                "cell_id": "v17-batch-" + sha256({"condition": condition, "prompt_group_id": group, "item_ids": [row["item_id"] for row in ordered]})[:20],
                "condition": condition, **batch_candidate, "prompt_group_id": group, "partition": "train", "item_ids": [row["item_id"] for row in ordered],
                "source_binding_sha256s": {row["item_id"]: row["source_binding_sha256"] for row in ordered}, "payload_base64": base64.b64encode(payload).decode("ascii"),
                "payload_sha256": digest, "endpoint_payload_sha256s": {"grok_primary": digest, "sol_later": digest},
            })
    if len(reused) != 12 or len(cells) != 48 or sum(row["condition"] == DIRECT for row in cells) != 38 or sum(row["condition"] in {FORWARD, REVERSE} for row in cells) != 10:
        raise ValueError("V17 logical cell geometry drifted")
    public_panel = [{key: row[key] for key in ("item_id", "prompt_group_id", "source_binding_sha256", "target", "historical_v15_direct")} for row in panel]
    value: dict[str, Any] = {
        "format_version": 1, "study_id": STUDY_ID, "kind": contract_value["kind"], "endpoint": "endpoint_separate",
        "groups": [{"prompt_group_id": group, "partition": "train"} for group in selection["groups"]], "panel": public_panel,
        "reused_direct_cells": reused, "cells": cells, "geometry": contract_value["geometry"], "analysis_rule": contract_value["analysis_rule"], "authority": contract_value["authority"],
        "source": {
            "v15_study_sha256": v16.V15_SHA256, "v15_schedule_sha256": v15_schedule["schedule_sha256"],
            "v16_study_sha256": V16_SHA256, "v16_contract_sha256": V16_CONTRACT_SHA256,
            "split_manifest_sha256": sha256(Path(split_manifest).read_bytes()), "hanna_csv_sha256": sha256(Path(hanna_csv).read_bytes()),
            "successor_contract_sha256": sha256(Path(successor_contract).read_bytes()), "group_selection": "v15_train_group_count_desc_then_prompt_id_asc_skip_first_five_v16_groups",
            "v16_predecessor_groups": selection["v16_predecessor_groups"],
        },
        "outbound_template_commitments": {"direct_v15": _direct_template_commitments(v15, v16), "comparative_v16": comparative_template},
    }
    value["schedule_sha256"] = sha256(value)
    return value


def validate_answer(condition: str, answer: Mapping[str, Any], *, expected_item_ids: Sequence[str] | None = None) -> dict[str, Any]:
    """Use V16's pinned response schema and validation without duplicating it."""
    return _v16().validate_answer(condition, answer, expected_item_ids=expected_item_ids)


def _measurement(value: Mapping[str, Any], expected_condition: str, expected_ids: Sequence[str] | None) -> dict[str, Any]:
    return _v16()._measurement(value, expected_condition, expected_ids)


def _dimension_metrics(rows: Sequence[Mapping[str, Any]], groups: Sequence[str]) -> dict[str, Any]:
    return _v16()._dimension_metrics(rows, groups)


def analyze(
    schedule_value: Mapping[str, Any],
    measurements: Mapping[str, Any],
    *,
    expected_endpoint: str,
    split_manifest: Path,
    hanna_csv: Path,
    successor_contract: Path,
) -> dict[str, Any]:
    """Compute arithmetic after binding supplied measurements to the frozen schedule."""
    if expected_endpoint not in {"grok_primary", "sol_later"}:
        raise ValueError("V17 endpoint is not recognized")
    if not isinstance(schedule_value, Mapping):
        raise TypeError("schedule must be an object")
    expected_schedule = schedule(
        split_manifest=Path(split_manifest),
        hanna_csv=Path(hanna_csv),
        successor_contract=Path(successor_contract),
    )
    if canonical(schedule_value) != canonical(expected_schedule):
        raise ValueError("schedule is not the exact rederived V17 schedule")
    committed = dict(schedule_value)
    schedule_sha = committed.pop("schedule_sha256", None)
    if schedule_sha != sha256(committed) or schedule_value.get("study_id") != STUDY_ID:
        raise ValueError("schedule commitment drifted")
    reused, fresh, panel = schedule_value.get("reused_direct_cells"), schedule_value.get("cells"), schedule_value.get("panel")
    if not isinstance(reused, list) or not isinstance(fresh, list) or not isinstance(panel, list) or len(reused) != 12 or len(fresh) != 48 or len(panel) != 50:
        raise ValueError("V17 schedule analysis geometry drifted")
    expected = {row["cell_id"]: row for row in [*reused, *fresh] if isinstance(row, Mapping)}
    if len(expected) != 60 or set(measurements) != set(expected):
        raise ValueError("analysis requires exactly all reused and new V17 measurements")
    targets = {row["item_id"]: row for row in panel if isinstance(row, Mapping)}
    if len(targets) != 50 or any(set(row.get("target", {})) != set(DIMS) for row in targets.values()):
        raise ValueError("V17 local panel target geometry drifted")
    direct_rows: list[dict[str, Any]] = []
    order_rows: dict[str, list[dict[str, Any]]] = {FORWARD: [], REVERSE: []}
    for cell_id, row in expected.items():
        condition = row.get("condition")
        measurement = measurements[cell_id]
        if not isinstance(measurement, Mapping):
            raise TypeError("measurement is not an object")
        provenance = measurement.get("provenance")
        if not isinstance(provenance, Mapping) or (
            provenance.get("cell_id") != cell_id
            or provenance.get("payload_sha256") != row.get("payload_sha256")
            or provenance.get("endpoint") != expected_endpoint
        ):
            raise ValueError("measurement provenance does not bind its scheduled cell and endpoint")
        v16_measurement = dict(measurement)
        v16_measurement["provenance"] = {
            key: item
            for key, item in provenance.items()
            if key in {"receipt_sha256", "raw_response_sha256", "endpoint"}
        }
        answer = _measurement(v16_measurement, str(condition), row.get("item_ids") if condition in {FORWARD, REVERSE} else None)
        if condition == DIRECT:
            item = targets.get(row.get("item_id"))
            if item is None:
                raise ValueError("direct measurement item is absent from panel")
            direct_rows.append({"item_id": item["item_id"], "prompt_group_id": item["prompt_group_id"], "scores": answer["scores"], "target": item["target"]})
        elif condition in order_rows:
            for item_answer in answer["items"]:
                item = targets.get(item_answer["item_id"])
                if item is None or item["prompt_group_id"] != row.get("prompt_group_id"):
                    raise ValueError("comparative measurement item is absent or crosses its prompt")
                order_rows[condition].append({"item_id": item["item_id"], "prompt_group_id": item["prompt_group_id"], "scores": item_answer["scores"], "target": item["target"]})
        else:
            raise ValueError("unknown scheduled V17 condition")
    groups = [row["prompt_group_id"] for row in schedule_value["groups"]]
    if len(direct_rows) != 50 or any(len(order_rows[condition]) != 50 for condition in order_rows):
        raise ValueError("V17 complete measurement panel is missing")
    forward = {row["item_id"]: row for row in order_rows[FORWARD]}
    reverse = {row["item_id"]: row for row in order_rows[REVERSE]}
    if len(forward) != 50 or len(reverse) != 50 or set(forward) != set(targets) or set(reverse) != set(targets):
        raise ValueError("comparative order pairing is incomplete")
    averaged = [
        {"item_id": item_id, "prompt_group_id": targets[item_id]["prompt_group_id"], "target": targets[item_id]["target"], "scores": {dimension: (forward[item_id]["scores"][dimension] + reverse[item_id]["scores"][dimension]) / 2 for dimension in DIMS}}
        for item_id in sorted(targets)
    ]
    return {
        "format_version": 1, "study_id": STUDY_ID, "kind": "arithmetic_only_v17_replication_analysis",
        "native_admission": "not_claimed; caller must independently admit persisted measurements", "expected_endpoint": expected_endpoint, "schedule_sha256": schedule_sha,
        "metrics": {
            "direct_historical_noncontemporaneous": _dimension_metrics(direct_rows, groups),
            FORWARD: _dimension_metrics(order_rows[FORWARD], groups), REVERSE: _dimension_metrics(order_rows[REVERSE], groups),
            "per_story_mean_orders": _dimension_metrics(averaged, groups),
        },
        "authority": contract()["authority"],
    }
