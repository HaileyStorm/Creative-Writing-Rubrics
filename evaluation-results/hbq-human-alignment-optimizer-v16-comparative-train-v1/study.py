"""Frozen TRAIN-only V16 direct and order-balanced comparative schedule core."""
from __future__ import annotations

import base64
import csv
import hashlib
import importlib.util
import io
import json
import math
import subprocess
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path
from types import ModuleType
from typing import Any

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
STUDY_ID = "hbq-human-alignment-optimizer-v16-comparative-train-v1"
CONTRACT = HERE / "experiment-contract.json"
V15 = REPO / "evaluation-results/hbq-human-alignment-optimizer-v15-rank-discrimination-v1/study.py"
V15_SHA256 = "4afeaff679efaf37e702c08841eb30a3317693e677ecfc3ded4dbb4ae4710caf"
V15_COMMIT = "3b28c30"
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


def _load(path: Path, digest: str, commit: str, name: str) -> ModuleType:
    raw = Path(path).read_bytes()
    blob = subprocess.run(["git", "-C", str(REPO), "show", f"{commit}:{Path(path).relative_to(REPO).as_posix()}"], capture_output=True, check=False)
    if blob.returncode or sha256(raw) != digest or blob.stdout != raw:
        raise ValueError("pinned dependency drifted")
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ValueError("pinned dependency cannot load")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def contract() -> dict[str, Any]:
    value = strict(CONTRACT.read_bytes(), "V16 experiment contract")
    expected = {
        "analysis_rule": {"comparative_primary": "per_story_mean_of_forward_and_reverse_then_within_prompt_average_tie_spearman_then_macro_across_six_dimensions", "direct_reuse": "historical_v15_direct_measurements_are_endpoint_separate_and_noncontemporaneous", "fixed_three": "rho_undefined", "hanna_compatible_dropundefined_with_retained_dropped_count": "per criterion, mean only defined prompt correlations; report retained and dropped prompt IDs and counts; macro undefined only when an entire criterion is undefined", "official_hanna_source_url": "https://raw.githubusercontent.com/dig-team/hanna-benchmark-asg/refs/heads/coling/data_visualization.ipynb", "strict_full_five": "coverage guard: macro is undefined whenever any of the five prompt correlations is undefined"},
        "authority": {"confirmation": "none", "development_train_only": True, "endpoint_pooling": "forbidden", "generalization": "none", "promotion": "none", "runtime": "none", "selection": "none"},
        "format_version": 1,
        "geometry": {"comparative_batches": 10, "direct_new": 29, "direct_reused": 21, "groups": 5, "items": 50, "logical_cells": 39, "max_concurrency": 10},
        "kind": "comparative_hanna_train_measurement",
        "study_id": STUDY_ID,
    }
    if value != expected:
        raise ValueError("V16 experiment contract drifted")
    return value


def _v15() -> ModuleType:
    return _load(V15, V15_SHA256, V15_COMMIT, "_v16_v15")


def _numeric_scores(value: Mapping[str, Any], *, decimals: bool) -> dict[str, float]:
    if set(value) != set(DIMS):
        raise ValueError("six HANNA scores are required")
    scores: dict[str, float] = {}
    for dimension in DIMS:
        raw = value[dimension]
        if type(raw) not in {int, float} or isinstance(raw, bool) or not math.isfinite(float(raw)) or not 1 <= float(raw) <= 5 or (not decimals and not float(raw).is_integer()):
            raise ValueError("HANNA score must be a finite real number in 1..5")
        scores[dimension] = float(raw)
    return scores


def _item_answer(value: Mapping[str, Any], *, decimals: bool) -> dict[str, Any]:
    if set(value) != {"item_id", "scores", "evidence", "coverage"} or not isinstance(value.get("item_id"), str):
        raise ValueError("comparative item answer shape drifted")
    scores = _numeric_scores(value["scores"], decimals=decimals) if isinstance(value.get("scores"), Mapping) else None
    evidence, coverage = value.get("evidence"), value.get("coverage")
    if scores is None or not isinstance(evidence, Mapping) or not isinstance(coverage, Mapping) or set(evidence) != set(DIMS) or set(coverage) != set(DIMS):
        raise ValueError("comparative item dimensions drifted")
    if any(not isinstance(evidence[dimension], str) or not evidence[dimension].strip() or (decimals and len(evidence[dimension]) > 320) or type(coverage[dimension]) is not bool for dimension in DIMS):
        raise ValueError("comparative item evidence or coverage drifted")
    return {"item_id": value["item_id"], "scores": scores, "evidence": dict(evidence), "coverage": dict(coverage)}


def validate_answer(condition: str, answer: Mapping[str, Any], *, expected_item_ids: Sequence[str] | None = None) -> dict[str, Any]:
    if not isinstance(answer, Mapping):
        raise TypeError("answer must be an object")
    if condition == DIRECT:
        if set(answer) != {"scores", "evidence", "coverage"}:
            raise ValueError("direct answer shape drifted")
        item = _item_answer({"item_id": "direct", **dict(answer)}, decimals=False)
        return {key: item[key] for key in ("scores", "evidence", "coverage")}
    if condition not in {FORWARD, REVERSE} or expected_item_ids is None:
        raise ValueError("unknown comparative condition")
    if set(answer) != {"items"} or not isinstance(answer["items"], list) or len(answer["items"]) != 10:
        raise ValueError("comparative answer requires exactly ten items")
    items = [_item_answer(value, decimals=True) for value in answer["items"] if isinstance(value, Mapping)]
    if len(items) != 10 or [item["item_id"] for item in items] != list(expected_item_ids) or len(set(expected_item_ids)) != 10:
        raise ValueError("comparative answer item membership or order drifted")
    return {"items": items}


def _panel(*, split_manifest: Path, hanna_csv: Path, successor_contract: Path) -> tuple[ModuleType, list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    v15 = _v15()
    original = v15._train48_items(split_manifest=split_manifest, hanna_csv=hanna_csv, successor_contract=successor_contract)
    counts = Counter(str(row["prompt_group_id"]) for row in original)
    groups = [group for group, _count in sorted(counts.items(), key=lambda pair: (-pair[1], pair[0]))[:5]]
    if [counts[group] for group in groups] != [5, 4, 4, 4, 4]:
        raise ValueError("V16 count-desc/hash-asc group selection drifted")
    raw = Path(hanna_csv).read_bytes()
    rows = list(csv.DictReader(io.StringIO(raw.decode("utf-8-sig"))))
    expected_columns = {"Story ID", "Prompt", "Human", "Story", "Model", *DIMS, "Worker ID", "Assignment ID", "Work time in seconds", "Name"}
    if not rows or set(rows[0]) != expected_columns:
        raise ValueError("pinned HANNA CSV schema drifted")
    existing = {(row["prompt"], row["story"]): row for row in original if row["prompt_group_id"] in set(groups)}
    systems: dict[str, dict[tuple[str, str], list[Mapping[str, str]]]] = {group: defaultdict(list) for group in groups}
    for row in rows:
        group = "prompt-" + hashlib.sha256(row["Prompt"].encode("utf-8")).hexdigest()[:16]
        if group in systems and row["Model"] != "Human":
            systems[group][(row["Story ID"], row["Model"])].append(row)
    panel: list[dict[str, Any]] = []
    for group in groups:
        if len(systems[group]) != 10 or len({key[0] for key in systems[group]}) != 10 or len({key[1] for key in systems[group]}) != 10:
            raise ValueError("V16 group lacks ten non-Human original systems")
        for (story_id, model), values in sorted(systems[group].items(), key=lambda pair: (pair[0][1], pair[0][0])):
            if len(values) != 3 or len({row["Prompt"] for row in values}) != 1 or len({row["Story"] for row in values}) != 1:
                raise ValueError("V16 source system annotation geometry drifted")
            prompt, story = values[0]["Prompt"], values[0]["Story"]
            target = {dimension: sum(float(row[dimension]) for row in values) / 3 for dimension in DIMS}
            inherited = existing.get((prompt, story))
            if inherited is not None:
                item_id, binding, historical = inherited["item_id"], inherited["source_binding_sha256"], True
                if inherited["target"] != target:
                    raise ValueError("V16 reused V15 target drifted")
            else:
                item_id = "item-" + sha256({"prompt_group_id": group, "story_id": story_id, "source_model": model})[:16]
                binding = sha256({"prompt_group_id": group, "story_id": story_id, "model": model, "prompt": prompt, "story": story})
                historical = False
            panel.append({"item_id": item_id, "prompt_group_id": group, "source_binding_sha256": binding, "target": target, "prompt": prompt, "story": story, "historical_v15_direct": historical})
    if len(panel) != 50 or len({row["item_id"] for row in panel}) != 50 or sum(row["historical_v15_direct"] for row in panel) != 21:
        raise ValueError("V16 panel geometry drifted")
    return v15, sorted(panel, key=lambda row: (row["prompt_group_id"], row["item_id"])), original, {"groups": groups, "counts": {group: counts[group] for group in groups}}


def _direct_candidate(v15: ModuleType) -> dict[str, Any]:
    instruction, _anchor = v15._shared_anchor_payload()
    profile, _schema = v15._condition(v15.DIRECT, v15.ANCHORS)
    instruction_sha256, profile_sha256 = sha256(instruction.encode("utf-8")), sha256(profile)
    return {"candidate_id": DIRECT, "instruction_sha256": instruction_sha256, "profile_sha256": profile_sha256, "candidate_sha256": sha256({"candidate_id": DIRECT, "instruction_sha256": instruction_sha256, "profile_sha256": profile_sha256})}


def _batch_candidate(v15: ModuleType) -> tuple[dict[str, Any], str, dict[str, Any]]:
    instruction, _anchor = v15._shared_anchor_payload()
    profile, _schema = v15._condition(v15.DIRECT, v15.ANCHORS)
    profile = {**profile, "condition": {"kind": "comparative_order_balanced", "instruction": "Compare the ten stories under each criterion to calibrate differences, then score each from its own text and the shared anchors. Do not force a range or ranking. Return numeric decimal scores from 1 through 5 for all ten in input order, with brief criterion-specific evidence."}, "comparative_order_is_not_quality": True}
    candidate_id = "comparative_hanna_decimal_bundle"
    instruction_sha256, profile_sha256 = sha256(instruction.encode("utf-8")), sha256(profile)
    return ({"candidate_id": candidate_id, "instruction_sha256": instruction_sha256, "profile_sha256": profile_sha256, "candidate_sha256": sha256({"candidate_id": candidate_id, "instruction_sha256": instruction_sha256, "profile_sha256": profile_sha256})}, instruction, profile)


def _batch_schema() -> dict[str, Any]:
    scores = {"type": "object", "additionalProperties": False, "required": list(DIMS), "properties": {dimension: {"type": "number", "minimum": 1, "maximum": 5} for dimension in DIMS}}
    evidence = {"type": "object", "additionalProperties": False, "required": list(DIMS), "properties": {dimension: {"type": "string", "minLength": 1, "maxLength": 320} for dimension in DIMS}}
    coverage = {"type": "object", "additionalProperties": False, "required": list(DIMS), "properties": {dimension: {"type": "boolean"} for dimension in DIMS}}
    item = {"type": "object", "additionalProperties": False, "required": ["item_id", "scores", "evidence", "coverage"], "properties": {"item_id": {"type": "string", "minLength": 1}, "scores": scores, "evidence": evidence, "coverage": coverage}}
    return {"format_version": 1, "type": "object", "additionalProperties": False, "required": ["items"], "properties": {"items": {"type": "array", "minItems": 10, "maxItems": 10, "items": item}}}


def _batch_payload(*, instruction: str, profile: Mapping[str, Any], prompt: str, ordered: Sequence[Mapping[str, Any]]) -> bytes:
    if len(ordered) != 10:
        raise ValueError("V16 comparative payload geometry drifted")
    serial = [{"item_id": row["item_id"], "story": row["story"]} for row in ordered]
    value = {"format_version": 1, "study_id": STUDY_ID, "instruction": instruction, "profile": dict(profile), "writing": {"prompt": prompt, "story": canonical(serial).decode("utf-8")}, "response_schema": _batch_schema()}
    if set(value) != {"format_version", "study_id", "instruction", "profile", "writing", "response_schema"} or set(value["writing"]) != {"prompt", "story"} or "target" in value:
        raise ValueError("V16 comparative payload leaked non-outbound data")
    return canonical(value)


def schedule(*, split_manifest: Path, hanna_csv: Path, successor_contract: Path) -> dict[str, Any]:
    contract_value = contract()
    v15, panel, _original, selection = _panel(split_manifest=Path(split_manifest), hanna_csv=Path(hanna_csv), successor_contract=Path(successor_contract))
    v15_schedule = v15.schedule(split_manifest=Path(split_manifest), hanna_csv=Path(hanna_csv), successor_contract=Path(successor_contract))
    direct_rows = {row["item_id"]: row for row in v15_schedule["cells"] if row["condition"] == v15.DIRECT}
    candidate = _direct_candidate(v15)
    batch_candidate, batch_instruction, batch_profile = _batch_candidate(v15)
    reused, cells = [], []
    for row in panel:
        if row["historical_v15_direct"]:
            source = direct_rows.get(row["item_id"])
            if not isinstance(source, Mapping) or source.get("payload_sha256") != sha256(base64.b64decode(source["payload_base64"], validate=True)):
                raise ValueError("V16 exact V15 direct reuse drifted")
            reused.append({"cell_id": source["cell_id"], "source_cell_id": source["cell_id"], "condition": DIRECT, **candidate, "item_id": row["item_id"], "prompt_group_id": row["prompt_group_id"], "partition": "train", "source_binding_sha256": row["source_binding_sha256"], "payload_base64": source["payload_base64"], "payload_sha256": source["payload_sha256"], "endpoint_payload_sha256s": source["endpoint_payload_sha256s"], "reuse_provenance": {"v15_study_sha256": V15_SHA256, "v15_cell_id": source["cell_id"], "v15_payload_sha256": source["payload_sha256"]}})
        else:
            payload = v15._payload(instruction=v15.SHARED_INSTRUCTION, anchors=v15.ANCHORS, condition=v15.DIRECT, item=row)
            digest = sha256(payload)
            cells.append({"cell_id": "v16-direct-" + sha256({"item": row["item_id"]})[:20], "condition": DIRECT, **candidate, "item_id": row["item_id"], "prompt_group_id": row["prompt_group_id"], "partition": "train", "source_binding_sha256": row["source_binding_sha256"], "payload_base64": base64.b64encode(payload).decode("ascii"), "payload_sha256": digest, "endpoint_payload_sha256s": {"grok_primary": digest, "sol_later": digest}})
    for group in selection["groups"]:
        group_rows = [row for row in panel if row["prompt_group_id"] == group]
        if len(group_rows) != 10 or len({row["prompt"] for row in group_rows}) != 1:
            raise ValueError("V16 comparative group panel drifted")
        forward = sorted(group_rows, key=lambda row: row["item_id"])
        for condition, ordered in ((FORWARD, forward), (REVERSE, list(reversed(forward)))):
            payload = _batch_payload(instruction=batch_instruction, profile=batch_profile, prompt=forward[0]["prompt"], ordered=ordered)
            digest = sha256(payload)
            cells.append({"cell_id": "v16-batch-" + sha256({"condition": condition, "prompt_group_id": group, "item_ids": [row["item_id"] for row in ordered]})[:20], "condition": condition, **batch_candidate, "prompt_group_id": group, "partition": "train", "item_ids": [row["item_id"] for row in ordered], "source_binding_sha256s": {row["item_id"]: row["source_binding_sha256"] for row in ordered}, "payload_base64": base64.b64encode(payload).decode("ascii"), "payload_sha256": digest, "endpoint_payload_sha256s": {"grok_primary": digest, "sol_later": digest}})
    if len(reused) != 21 or len(cells) != 39 or sum(row["condition"] == DIRECT for row in cells) != 29 or sum(row["condition"] in {FORWARD, REVERSE} for row in cells) != 10:
        raise ValueError("V16 logical cell geometry drifted")
    public_panel = [{key: row[key] for key in ("item_id", "prompt_group_id", "source_binding_sha256", "target", "historical_v15_direct")} for row in panel]
    value: dict[str, Any] = {"format_version": 1, "study_id": STUDY_ID, "kind": contract_value["kind"], "endpoint": "endpoint_separate", "groups": [{"prompt_group_id": group, "partition": "train"} for group in selection["groups"]], "panel": public_panel, "reused_direct_cells": reused, "cells": cells, "geometry": contract_value["geometry"], "analysis_rule": contract_value["analysis_rule"], "authority": contract_value["authority"], "source": {"v15_study_sha256": V15_SHA256, "v15_schedule_sha256": v15_schedule["schedule_sha256"], "split_manifest_sha256": sha256(Path(split_manifest).read_bytes()), "hanna_csv_sha256": sha256(Path(hanna_csv).read_bytes()), "successor_contract_sha256": sha256(Path(successor_contract).read_bytes()), "group_selection": "v15_train_group_count_desc_then_prompt_id_asc"}}
    value["schedule_sha256"] = sha256(value)
    return value


def _mean(values: Sequence[float]) -> float:
    if not values:
        raise ValueError("mean requires values")
    return sum(values) / len(values)


def _ranks(values: Sequence[float]) -> list[float]:
    ordered = sorted(enumerate(values), key=lambda pair: pair[1])
    result = [0.0] * len(values)
    start = 0
    while start < len(ordered):
        end = start + 1
        while end < len(ordered) and ordered[end][1] == ordered[start][1]:
            end += 1
        rank = (start + 1 + end) / 2
        for index, _value in ordered[start:end]:
            result[index] = rank
        start = end
    return result


def _spearman(left: Sequence[float], right: Sequence[float]) -> float | None:
    if len(left) != len(right) or len(left) < 2:
        raise ValueError("paired rank values required")
    a, b = _ranks(left), _ranks(right)
    mean_a, mean_b = _mean(a), _mean(b)
    variance_a = sum((value - mean_a) ** 2 for value in a)
    variance_b = sum((value - mean_b) ** 2 for value in b)
    if variance_a == 0 or variance_b == 0:
        return None
    return sum((x - mean_a) * (y - mean_b) for x, y in zip(a, b, strict=True)) / math.sqrt(variance_a * variance_b)


def _dimension_metrics(rows: Sequence[Mapping[str, Any]], groups: Sequence[str]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for dimension in DIMS:
        all_scores = [float(row["scores"][dimension]) for row in rows]
        all_targets = [float(row["target"][dimension]) for row in rows]
        by_group = {
            group: _spearman(
                [float(row["scores"][dimension]) for row in rows if row["prompt_group_id"] == group],
                [float(row["target"][dimension]) for row in rows if row["prompt_group_id"] == group],
            )
            for group in groups
        }
        retained = [group for group in groups if by_group[group] is not None]
        dropped = [group for group in groups if by_group[group] is None]
        result[dimension] = {
            "global_item_50_spearman": _spearman(all_scores, all_targets),
            "global_item_50_mae": _mean([abs(score - target) for score, target in zip(all_scores, all_targets, strict=True)]),
            "global_item_50_model_tied_pairs": sum(
                all_scores[left] == all_scores[right] for left in range(len(all_scores)) for right in range(left + 1, len(all_scores))
            ),
            "per_prompt_spearman": by_group,
            "hanna_compatible_mean_defined_prompt_spearman": None if not retained else _mean([float(by_group[group]) for group in retained]),
            "hanna_compatible_retained_prompt_ids": retained,
            "hanna_compatible_dropped_prompt_ids": dropped,
            "hanna_compatible_retained_prompt_count": len(retained),
            "hanna_compatible_dropped_prompt_count": len(dropped),
            "fixed_three_spearman": None,
        }
    strict_complete = all(not result[dimension]["hanna_compatible_dropped_prompt_ids"] for dimension in DIMS)
    all_defined = [result[dimension]["hanna_compatible_mean_defined_prompt_spearman"] for dimension in DIMS]
    return {"dimensions": result, "hanna_compatible_macro_six": None if any(value is None for value in all_defined) else _mean([float(value) for value in all_defined]), "strict_full_five_prompt_macro_six": None if not strict_complete or any(value is None for value in all_defined) else _mean([float(value) for value in all_defined]), "strict_full_five_prompt_complete": strict_complete}


def _measurement(value: Mapping[str, Any], expected_condition: str, expected_ids: Sequence[str] | None) -> dict[str, Any]:
    if set(value) != {"condition", "answer", "provenance"} or value.get("condition") != expected_condition or not isinstance(value.get("answer"), Mapping) or not isinstance(value.get("provenance"), Mapping):
        raise ValueError("measurement shape or condition drifted")
    provenance = value["provenance"]
    if set(provenance) - {"receipt_sha256", "raw_response_sha256", "endpoint"} or any(not isinstance(provenance[key], str) or not provenance[key] for key in provenance):
        raise ValueError("measurement provenance fields drifted")
    return validate_answer(expected_condition, value["answer"], expected_item_ids=expected_ids)


def analyze(schedule_value: Mapping[str, Any], measurements: Mapping[str, Any]) -> dict[str, Any]:
    """Arithmetic only: receipt provenance fields are bound, never treated as native admission proof."""
    if not isinstance(schedule_value, Mapping):
        raise TypeError("schedule must be an object")
    committed = dict(schedule_value)
    schedule_sha = committed.pop("schedule_sha256", None)
    if schedule_sha != sha256(committed) or schedule_value.get("study_id") != STUDY_ID:
        raise ValueError("schedule commitment drifted")
    reused, fresh = schedule_value.get("reused_direct_cells"), schedule_value.get("cells")
    panel = schedule_value.get("panel")
    if not isinstance(reused, list) or not isinstance(fresh, list) or not isinstance(panel, list) or len(reused) != 21 or len(fresh) != 39 or len(panel) != 50:
        raise ValueError("V16 schedule analysis geometry drifted")
    expected = {row["cell_id"]: row for row in [*reused, *fresh] if isinstance(row, Mapping)}
    if len(expected) != 60 or set(measurements) != set(expected):
        raise ValueError("analysis requires exactly all reused and new V16 measurements")
    targets = {row["item_id"]: row for row in panel if isinstance(row, Mapping)}
    if len(targets) != 50 or any(set(row.get("target", {})) != set(DIMS) for row in targets.values()):
        raise ValueError("V16 local panel target geometry drifted")
    direct_rows: list[dict[str, Any]] = []
    order_rows: dict[str, list[dict[str, Any]]] = {FORWARD: [], REVERSE: []}
    for cell_id, row in expected.items():
        condition = row.get("condition")
        expected_ids = row.get("item_ids") if condition in {FORWARD, REVERSE} else None
        answer = _measurement(measurements[cell_id], str(condition), expected_ids)
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
            raise ValueError("unknown scheduled V16 condition")
    groups = [row["prompt_group_id"] for row in schedule_value["groups"]]
    if len(direct_rows) != 50 or any(len(order_rows[condition]) != 50 for condition in order_rows):
        raise ValueError("V16 complete measurement panel is missing")
    averaged: list[dict[str, Any]] = []
    for item_id, target in targets.items():
        forward = next((row for row in order_rows[FORWARD] if row["item_id"] == item_id), None)
        reverse = next((row for row in order_rows[REVERSE] if row["item_id"] == item_id), None)
        if forward is None or reverse is None:
            raise ValueError("comparative order pairing is incomplete")
        averaged.append({"item_id": item_id, "prompt_group_id": target["prompt_group_id"], "target": target["target"], "scores": {dimension: _mean([forward["scores"][dimension], reverse["scores"][dimension]]) for dimension in DIMS}})
    return {"format_version": 1, "study_id": STUDY_ID, "kind": "arithmetic_only_v16_measurement_analysis", "native_admission": "not_claimed; caller must independently admit persisted measurements", "schedule_sha256": schedule_sha, "metrics": {"direct_historical_noncontemporaneous": _dimension_metrics(direct_rows, groups), FORWARD: _dimension_metrics(order_rows[FORWARD], groups), REVERSE: _dimension_metrics(order_rows[REVERSE], groups), "per_story_mean_orders": _dimension_metrics(averaged, groups)}, "authority": contract()["authority"]}
