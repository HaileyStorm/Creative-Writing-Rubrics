"""Frozen 26-cell Grok development measurement for baseline versus child20."""

from __future__ import annotations

import argparse
import asyncio
import base64
import csv
import hashlib
import importlib.util
import io
import json
import math
import subprocess
import sys
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path
from types import ModuleType
from typing import Any

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
STUDY_ID = "hbq-human-alignment-optimizer-v12-development-panel-v1"
CONTRACT_PATH = HERE / "study-contract.json"
V11 = REPO / "evaluation-results/hbq-human-alignment-optimizer-v11-child20-train-screen-v1/study.py"
V11_SHA256 = "af2d326934f51ddb83b6449a760295f46921c87189c653558de37930af018f11"
V11_COMMIT = "dc7b59a"
V10 = REPO / "evaluation-results/hbq-human-alignment-optimizer-v10-fresh96-confirmation-candidates-v1/study.py"
V10_SHA256 = "38ea9c9c0cf96dfc0ca32b64ee6639515600bc01b93e204cdd397bae393b2a6f"
V10_COMMIT = "1c10bae"
V1 = REPO / "evaluation-results/hbq-human-alignment-optimizer-v1/study.py"
V1_SHA256 = "0651e7eb412ed8cf71b0cbc0db0440953a977224c83dda25eda141cb4b9f8acf"
V1_COMMIT = "36037b1"
RECONCILE = REPO / "evaluation-results/hbq-human-alignment-optimizer-v10-fresh96-confirmation-grok-reconcile-v1/reconcile.py"
RECONCILE_SHA256 = "6c132ade2b95bad54a580736e9e8b66fef4cb8b9733f91c0398dd35e4488293d"
RECONCILE_COMMIT = "c7d9191"
SPLIT_SHA256 = "6ffa942b595449f4118c2cd51f3a36716126612a7c10f4765953c17eb1efdbc2"
CSV_SHA256 = "ef59054d27fa32def06cfdc57243b1dd09c7e71f40b6d9d43fecfbf60e59026b"
SUCCESSOR_SHA256 = "b0f6dd24415c388a3104f8c9304ce301193cf0a48631a86c4886bc8ce48468e7"
BASELINE = "candidate-102cc7f06c9a99a7"
CHILD20 = "broader-nextwave-20-missing_evidence_not_no-referent-evidence"
DIMS = ("Relevance", "Coherence", "Empathy", "Surprise", "Engagement", "Complexity")
DEVELOPMENT_ITEMS = {
    "prompt-132112dd8eeb2d4d": ("item-028fc3ac6963b50f", "item-25d5a1163ca56b27"),
    "prompt-3f844c5cdc6b51ae": ("item-2ba42c130da729fa", "item-8776b34674d81280"),
    "prompt-6450c4baa52d6998": ("item-d5fe1ae06099a06e", "item-f6e3af87c879383c"),
    "prompt-6a99e79cf010b289": ("item-1568277c2dde9944", "item-242fe0ddf52e6278"),
    "prompt-7c393c4bcb3a7484": ("item-2377fcf24510aac5", "item-85b393b19a363e89"),
    "prompt-8997770ce6efe4d5": ("item-0cb9c7afe8527434",),
    "prompt-8d3d397a4f6ba0ea": ("item-1b27b9076eef2bc5", "item-9a254f1a6661a875"),
}


def canonical(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")


def sha256(value: bytes | Any) -> str:
    return hashlib.sha256(value if isinstance(value, bytes) else canonical(value)).hexdigest()


def strict(raw: bytes, label: str) -> dict[str, Any]:
    try:
        value = json.loads(raw.decode("utf-8"), parse_constant=lambda token: (_ for _ in ()).throw(ValueError(token)))
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise ValueError(f"invalid {label}") from exc
    if not isinstance(value, dict) or canonical(value) != raw:
        raise ValueError(f"invalid {label}")
    return value


def contract() -> dict[str, Any]:
    try:
        value = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("invalid study contract") from exc
    expected = {
        "format_version": 1,
        "study_id": STUDY_ID,
        "kind": "fresh_matched_child20_development_panel",
        "requested_judge": {
            "endpoint": "grok_primary",
            "model": "grok-4.6",
            "reported_model": "grok-4.6-build",
            "reasoning": "high",
            "provider_attested": False,
            "tools": "off",
        },
        "geometry": {"candidates": 2, "development_groups": 7, "development_items": 13, "grok_cells": 26, "sol_cells": 0},
        "historical_baseline_context": {
            "prior_baseline_cells": 3,
            "schedule_sha256": "e8de7435e7cb1cab43f2a4d99438b2d136f6b763e758766cf3fe8626e1eda9e5",
            "status": "planned_repeats_context_only",
            "adopted_into_metrics": False,
            "extra_votes": False,
        },
        "authority": {
            "development_only": True,
            "confirmation_cells": 0,
            "confirmation_access": "forbidden_in_this_study",
            "previous_results": "unchanged",
            "selection": "none",
            "promotion": "none",
            "sol_execution": "unopened",
            "dspy_optuna_runtime": False,
        },
        "analysis_rule": {
            "primary": "absolute_error_per_item_then_mean_within_each_prompt_group_then_equal_mean_across_7_prompt_groups",
            "coverage": "include_every_finite_numeric_score_even_when_coverage_is_false",
            "rank_correlations": {
                "item_13": "Spearman of item model score versus item human target, per dimension",
                "group_mean_7": "Spearman of per-group mean model score versus per-group mean human target, per dimension",
            },
        },
    }
    if value != expected:
        raise ValueError("V12 public contract drifted")
    return value


def pinned(path: Path, commit: str, digest: str) -> bytes:
    raw = Path(path).read_bytes()
    relative = Path(path).relative_to(REPO).as_posix()
    result = subprocess.run(["git", "-C", str(REPO), "show", f"{commit}:{relative}"], capture_output=True, check=False)
    if result.returncode or sha256(raw) != digest or result.stdout != raw:
        raise ValueError("pinned dependency drifted")
    return raw


def load(path: Path, commit: str, digest: str, name: str) -> ModuleType:
    raw = pinned(path, commit, digest)
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ValueError("pinned module cannot load")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(name, None)
    if Path(path).read_bytes() != raw:
        raise ValueError("pinned module changed during load")
    return module


def _split_items(raw: bytes) -> list[dict[str, str]]:
    try:
        split = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("frozen split is invalid") from exc
    groups = split.get("groups") if isinstance(split, Mapping) else None
    items = split.get("items") if isinstance(split, Mapping) else None
    expected_groups = set(DEVELOPMENT_ITEMS)
    expected_items = {(group, item) for group, item_ids in DEVELOPMENT_ITEMS.items() for item in item_ids}
    actual_groups = {
        row.get("prompt_group_id")
        for row in groups or []
        if isinstance(row, Mapping) and row.get("partition") == "development"
    }
    actual_items = {
        (row.get("prompt_group_id"), row.get("item_id"))
        for row in items or []
        if isinstance(row, Mapping) and row.get("partition") == "development"
    }
    if actual_groups != expected_groups or actual_items != expected_items:
        raise ValueError("frozen V12 development partition drifted")
    return [
        {"prompt_group_id": group, "item_id": item}
        for group, item in sorted(expected_items)
    ]


def source_items(*, split_manifest: Path, hanna_csv: Path, successor_contract: Path) -> list[dict[str, Any]]:
    split_raw = Path(split_manifest).read_bytes()
    csv_raw = Path(hanna_csv).read_bytes()
    successor_raw = Path(successor_contract).read_bytes()
    if (sha256(split_raw), sha256(csv_raw), sha256(successor_raw)) != (SPLIT_SHA256, CSV_SHA256, SUCCESSOR_SHA256):
        raise ValueError("frozen V12 source pin drifted")
    selected_partition = _split_items(split_raw)
    v1 = load(V1, V1_COMMIT, V1_SHA256, "_v12_v1_source")
    alias_map = {row["item_id"]: row for row in v1.derive_eligible_map(Path(successor_contract), Path(hanna_csv))}
    if set(alias_map).intersection({row["item_id"] for row in selected_partition}) != {row["item_id"] for row in selected_partition}:
        raise ValueError("pinned V1 source alias map drifted")
    try:
        rows = list(csv.DictReader(io.StringIO(csv_raw.decode("utf-8-sig"))))
    except (UnicodeDecodeError, csv.Error) as exc:
        raise ValueError("pinned HANNA CSV is invalid") from exc
    selected: list[dict[str, Any]] = []
    for row in selected_partition:
        alias = alias_map[row["item_id"]]
        if alias.get("prompt_group_id") != row["prompt_group_id"]:
            raise ValueError("V12 item/group alias drifted")
        matches = [
            source for source in rows
            if source.get("Story ID") == alias.get("story_id")
            and source.get("Model") == alias.get("source_model")
            and "prompt-" + hashlib.sha256(str(source.get("Prompt", "")).encode("utf-8")).hexdigest()[:16] == row["prompt_group_id"]
        ]
        stories = {source.get("Story") for source in matches}
        if len(matches) != 3 or len(stories) != 1 or any(source.get("Model") == "Human" for source in matches):
            raise ValueError("frozen V12 item source drifted")
        target = {dimension: sum(float(source[dimension]) for source in matches) / 3 for dimension in DIMS}
        first = matches[0]
        selected.append({
            "item_id": row["item_id"],
            "prompt_group_id": row["prompt_group_id"],
            "partition": "development",
            "prompt": first["Prompt"],
            "story": first["Story"],
            "target": target,
            "source_binding_sha256": sha256({"prompt_group_id": row["prompt_group_id"], "story_id": first["Story ID"], "model": first["Model"], "prompt": first["Prompt"], "story": first["Story"]}),
        })
    if len(selected) != 13 or len({row["item_id"] for row in selected}) != 13:
        raise ValueError("V12 item cardinality drifted")
    return sorted(selected, key=lambda row: (row["prompt_group_id"], row["item_id"]))


def schedule(*, split_manifest: Path, hanna_csv: Path, successor_contract: Path) -> dict[str, Any]:
    contract_value = contract()
    v10 = load(V10, V10_COMMIT, V10_SHA256, "_v12_v10_payload")
    validation = v10._module(v10.VALIDATION, v10.VALIDATION_SHA256, "_v12_validation")
    panel = [row for row in v10._panel(validation) if row["candidate_id"] in {BASELINE, CHILD20}]
    if len(panel) != 2 or [row["candidate_id"] for row in panel] != [BASELINE, CHILD20]:
        raise ValueError("V10 paired candidate panel drifted")
    cells: list[dict[str, Any]] = []
    for item in source_items(split_manifest=split_manifest, hanna_csv=hanna_csv, successor_contract=successor_contract):
        for candidate in panel:
            payload = v10._payload(validation, item, candidate)
            cells.append({
                "cell_id": "v12-development-" + sha256({"candidate": candidate["candidate_id"], "item": item["item_id"]})[:20],
                "ordinal": len(cells) + 1,
                "candidate_id": candidate["candidate_id"],
                "candidate_sha256": candidate["candidate_sha256"],
                "candidate_instruction_sha256": candidate["instruction_sha256"],
                "candidate_profile_sha256": candidate["profile_sha256"],
                "item_id": item["item_id"],
                "prompt_group_id": item["prompt_group_id"],
                "partition": "development",
                "source_binding_sha256": item["source_binding_sha256"],
                "target": item["target"],
                "target_sha256": sha256(item["target"]),
                "payload_base64": base64.b64encode(payload).decode("ascii"),
                "payload_sha256": sha256(payload),
                "endpoint_payload_sha256s": {"grok_primary": sha256(payload), "sol_later": sha256(payload)},
            })
    if len(cells) != 26 or len({row["cell_id"] for row in cells}) != 26:
        raise ValueError("V12 cell geometry drifted")
    value: dict[str, Any] = {
        "format_version": 1,
        "study_id": STUDY_ID,
        "kind": contract_value["kind"],
        "endpoint": "grok_primary",
        "requested_judge": contract_value["requested_judge"],
        "groups": [{"prompt_group_id": group, "partition": "development"} for group in sorted(DEVELOPMENT_ITEMS)],
        "cells": cells,
        "geometry": contract_value["geometry"],
        "historical_baseline_context": contract_value["historical_baseline_context"],
        "analysis_rule": contract_value["analysis_rule"],
        "authority": contract_value["authority"],
        "source": {"split_manifest_sha256": SPLIT_SHA256, "hanna_csv_sha256": CSV_SHA256, "successor_contract_sha256": SUCCESSOR_SHA256},
    }
    value["schedule_sha256"] = sha256(value)
    return value


@contextmanager
def bound(*, schedule_value: Mapping[str, Any]) -> Iterator[tuple[ModuleType, ModuleType, ModuleType, ModuleType]]:
    v11 = load(V11, V11_COMMIT, V11_SHA256, "_v12_v11_lifecycle")
    with v11.bound(schedule_value=schedule_value) as (lifecycle, runtime, v9):
        original_study = lifecycle.STUDY_ID
        lifecycle.STUDY_ID = STUDY_ID
        try:
            yield lifecycle, runtime, v9, v11
        finally:
            lifecycle.STUDY_ID = original_study


def prepare_all(*, output_root: Path, queue_root: Path, authorization_acknowledgement_sha256: str, split_manifest: Path, hanna_csv: Path, successor_contract: Path, route_provider: Callable[[Path], tuple[dict[str, Any], dict[str, Any]]]) -> dict[str, Any]:
    value = schedule(split_manifest=split_manifest, hanna_csv=hanna_csv, successor_contract=successor_contract)
    with bound(schedule_value=value) as (lifecycle, runtime, v9, _v11):
        result = lifecycle.prepare_all(
            output_root=Path(output_root),
            queue_root=Path(queue_root),
            authorization_acknowledgement_sha256=authorization_acknowledgement_sha256,
            route_provider=v9._validated_route(v9.parent_stack(), runtime, Path(queue_root), route_provider),
            normalized_root=Path(output_root).parent / ".v11-normalized",
            materialization_root=Path(output_root).parent / ".v11-materialization",
            frozen_successor_path=Path(output_root).parent / ".v11-successor.json",
            hanna_csv_path=Path(output_root).parent / ".v11-source.csv",
        )
    prepared = result.get("prepared_cells", [])
    expected = {row["cell_id"] for row in value["cells"]}
    if len(prepared) != 26 or set(prepared) != expected or (Path(output_root) / "schedule.json").read_bytes() != canonical(value):
        raise ValueError("lower lifecycle did not prepare exactly 26 V12 cells")
    return {"study_id": STUDY_ID, "prepared_cells": prepared, "logical_cells": 26, "provider_calls_made": 0, "process_launches": 0}


def execute_wave(*, output_root: Path, queue_root: Path, authorization_acknowledgement_sha256: str, split_manifest: Path, hanna_csv: Path, successor_contract: Path, allow_remote: bool, route_provider: Callable[[Path], tuple[dict[str, Any], dict[str, Any]]], runner: Callable[..., Mapping[str, Any]] | None = None) -> list[dict[str, Any]]:
    if allow_remote is not True:
        raise ValueError("explicit allow_remote required")
    value = schedule(split_manifest=split_manifest, hanna_csv=hanna_csv, successor_contract=successor_contract)
    with bound(schedule_value=value) as (lifecycle, runtime, v9, v11):
        reconciler = load(RECONCILE, RECONCILE_COMMIT, RECONCILE_SHA256, "_v12_response_reconcile")
        response_helper = reconciler.helper()
        parent = v9.parent_stack()
        selected = parent._guard_runner(runner or lifecycle.live()._default_runner, lifecycle, value)

        async def launch() -> list[dict[str, Any]]:
            validated = v9._validated_route(v9.parent_stack(), runtime, Path(queue_root), route_provider)
            route, evidence = validated(Path(queue_root))
            gate = asyncio.Semaphore(10)

            async def one(cell_id: str) -> dict[str, Any]:
                async with gate:
                    return await asyncio.to_thread(
                        v11._execute_bound,
                        value=value,
                        lifecycle=lifecycle,
                        runtime=runtime,
                        v9=v9,
                        reconciler=reconciler,
                        response_helper=response_helper,
                        selected=selected,
                        output_root=Path(output_root),
                        queue_root=Path(queue_root),
                        authorization_acknowledgement_sha256=authorization_acknowledgement_sha256,
                        cell_id=cell_id,
                        route_provider=lambda _ignored: (route, evidence),
                    )

            outcomes = await asyncio.gather(*(one(row["cell_id"]) for row in value["cells"]), return_exceptions=True)
            failure = next((outcome for outcome in outcomes if isinstance(outcome, BaseException)), None)
            if failure is not None:
                raise failure
            return [outcome for outcome in outcomes if isinstance(outcome, dict)]

        return asyncio.run(launch())


def _mean(values: list[float]) -> float:
    if not values or not all(math.isfinite(value) for value in values):
        raise ValueError("finite numeric values required")
    return sum(values) / len(values)


def _rank(values: list[float]) -> list[float]:
    if not values or not all(math.isfinite(value) for value in values):
        raise ValueError("finite numeric values required")
    result = [0.0] * len(values)
    ordered = sorted(enumerate(values), key=lambda row: row[1])
    cursor = 0
    while cursor < len(ordered):
        end = cursor + 1
        while end < len(ordered) and ordered[end][1] == ordered[cursor][1]:
            end += 1
        average = (cursor + 1 + end) / 2
        for index, _value in ordered[cursor:end]:
            result[index] = average
        cursor = end
    return result


def _spearman(left: list[float], right: list[float]) -> float | None:
    if len(left) != len(right) or len(left) < 2:
        raise ValueError("rank correlation requires paired observations")
    ranked_left, ranked_right = _rank(left), _rank(right)
    mean_left, mean_right = _mean(ranked_left), _mean(ranked_right)
    numerator = sum((a - mean_left) * (b - mean_right) for a, b in zip(ranked_left, ranked_right, strict=True))
    denominator_left = sum((value - mean_left) ** 2 for value in ranked_left)
    denominator_right = sum((value - mean_right) ** 2 for value in ranked_right)
    if denominator_left == 0 or denominator_right == 0:
        return None
    value = numerator / math.sqrt(denominator_left * denominator_right)
    return value if math.isfinite(value) else None


def _rank_records(cells: list[dict[str, Any]], by_group: Mapping[str, list[dict[str, Any]]]) -> dict[str, Any]:
    item_rows = sorted(cells, key=lambda row: row["item_id"])
    values: dict[str, Any] = {"item_13": {}, "group_mean_7": {}}
    for dimension in DIMS:
        values["item_13"][dimension] = _spearman(
            [float(row["scores"][dimension]) for row in item_rows],
            [float(row["target"][dimension]) for row in item_rows],
        )
        grouped = [by_group[group] for group in sorted(DEVELOPMENT_ITEMS)]
        values["group_mean_7"][dimension] = _spearman(
            [_mean([float(row["scores"][dimension]) for row in rows]) for rows in grouped],
            [_mean([float(row["target"][dimension]) for row in rows]) for rows in grouped],
        )
    return values


def report(*, output_root: Path, authorization_acknowledgement_sha256: str, split_manifest: Path, hanna_csv: Path, successor_contract: Path) -> dict[str, Any]:
    value = schedule(split_manifest=split_manifest, hanna_csv=hanna_csv, successor_contract=successor_contract)
    roots = Path(output_root)
    expected = {row["cell_id"] for row in value["cells"]}
    if not roots.is_dir() or {path.name for path in roots.iterdir()} != {"schedule.json", ".claims", *expected} or (roots / "schedule.json").read_bytes() != canonical(value):
        raise ValueError("incomplete or ambiguous V12 receipt inventory")
    reconciler = load(RECONCILE, RECONCILE_COMMIT, RECONCILE_SHA256, "_v12_report_reconcile")
    helper = reconciler.helper()
    cells: list[dict[str, Any]] = []
    grouped: dict[str, dict[str, list[dict[str, Any]]]] = {BASELINE: {}, CHILD20: {}}
    request_ids: set[str] = set()
    session_ids: set[str] = set()
    with bound(schedule_value=value) as (lifecycle, _runtime, v9, _v11):
        source = lifecycle.live()
        parent = v9.parent_stack()
        v9._validate_claims(roots, expected)
        frozen_route: Mapping[str, Any] | None = None
        frozen_evidence: Mapping[str, Any] | None = None
        for row in value["cells"]:
            root = roots / row["cell_id"]
            stored = v9.strict(v9.stable(root / "prepared.json"), "prepared")
            acknowledgement = v9.strict(v9.stable(root / "authorization-acknowledgement.json"), "acknowledgement")
            if acknowledgement.get("acknowledgement_sha256") != authorization_acknowledgement_sha256:
                raise ValueError("receipt acknowledgement drifted")
            route, evidence = stored.get("route"), stored.get("route_evidence")
            if not isinstance(route, Mapping) or not isinstance(evidence, Mapping):
                raise TypeError("ambiguous receipt route or evidence")
            if frozen_route is None:
                frozen_route, frozen_evidence = route, evidence
            elif route != frozen_route or evidence != frozen_evidence:
                raise ValueError("mixed receipt route or evidence")
            raw, prompt, schema = lifecycle.payload(row)
            request, response, identity, _settings = lifecycle.admit(
                root,
                row,
                value,
                raw,
                prompt,
                schema,
                route,
                evidence,
                authorization_acknowledgement_sha256,
                source,
            )
            envelope, _identity = reconciler._response(helper, response, route)
            structured = envelope["structuredOutput"]
            scores, coverage = structured["scores"], structured["coverage"]
            if set(scores) != set(DIMS) or set(coverage) != set(DIMS):
                raise ValueError("native score or coverage schema drifted")
            if any(type(scores[dimension]) not in {int, float} or not math.isfinite(float(scores[dimension])) for dimension in DIMS):
                raise ValueError("native score is not finite")
            if any(type(coverage[dimension]) is not bool for dimension in DIMS):
                raise ValueError("native coverage schema drifted")
            request_id = identity.get("request_id") if isinstance(identity, Mapping) else None
            session_id = identity.get("session_id") if isinstance(identity, Mapping) else None
            if (not isinstance(request_id, str) or not request_id or request_id in request_ids
                    or not isinstance(session_id, str) or not session_id or session_id in session_ids):
                raise ValueError("duplicate or invalid native identity")
            request_ids.add(request_id)
            session_ids.add(session_id)
            per_item_mae = _mean([abs(float(scores[dimension]) - float(row["target"][dimension])) for dimension in DIMS])
            cell = {
                "cell_id": row["cell_id"],
                "candidate_id": row["candidate_id"],
                "item_id": row["item_id"],
                "prompt_group_id": row["prompt_group_id"],
                "partition": "development",
                "payload_sha256": row["payload_sha256"],
                "native_request_sha256": sha256(request),
                "native_response_sha256": sha256(response),
                "scores": {dimension: float(scores[dimension]) for dimension in DIMS},
                "coverage": {dimension: coverage[dimension] for dimension in DIMS},
                "target": {dimension: float(row["target"][dimension]) for dimension in DIMS},
                "per_item_mae": per_item_mae,
            }
            candidates = grouped.get(row["candidate_id"])
            if candidates is None:
                raise ValueError("unexpected candidate receipt")
            candidates.setdefault(row["prompt_group_id"], []).append(cell)
            cells.append(cell)
        if frozen_route is None or frozen_evidence is None:
            raise ValueError("missing V12 route evidence")
        lifecycle.validate_frozen_route(frozen_route, frozen_evidence)
        parent._validate_route_evidence(frozen_route, frozen_evidence)
    if len(cells) != 26 or len(request_ids) != 26 or len(session_ids) != 26:
        raise ValueError("incomplete V12 receipt projection")
    metrics: list[dict[str, Any]] = []
    correlations: dict[str, dict[str, Any]] = {}
    for candidate in (BASELINE, CHILD20):
        by_group = grouped[candidate]
        if set(by_group) != set(DEVELOPMENT_ITEMS):
            raise ValueError("candidate development-group coverage drifted")
        for group, item_ids in DEVELOPMENT_ITEMS.items():
            rows = by_group[group]
            if {row["item_id"] for row in rows} != set(item_ids) or len(rows) != len(item_ids):
                raise ValueError("candidate item grouping drifted")
        group_mae = {group: _mean([row["per_item_mae"] for row in by_group[group]]) for group in sorted(by_group)}
        candidate_cells = [row for row in cells if row["candidate_id"] == candidate]
        metrics.append({
            "candidate_id": candidate,
            "per_group_mean_item_mae": group_mae,
            "equal_group_mean_item_mae": _mean(list(group_mae.values())),
            "item_count": 13,
            "group_count": 7,
        })
        correlations[candidate] = _rank_records(candidate_cells, by_group)
    baseline, child = metrics
    primary_baseline = baseline["equal_group_mean_item_mae"]
    primary_child = child["equal_group_mean_item_mae"]
    strict_improvement = primary_child < primary_baseline
    return {
        "format_version": 1,
        "study_id": STUDY_ID,
        "kind": "receipt_derived_26_cell_grok_development_report",
        "endpoint": "grok_primary",
        "authority": contract()["authority"],
        "analysis_rule": contract()["analysis_rule"],
        "native_endpoint_contact_cardinality": "unproven",
        "cells": cells,
        "unique_request_ids": len(request_ids),
        "unique_session_ids": len(session_ids),
        "metrics": metrics,
        "rank_correlations": correlations,
        "comparison": {
            "baseline_candidate_id": BASELINE,
            "child_candidate_id": CHILD20,
            "child20_minus_baseline": primary_child - primary_baseline,
            "relative_reduction": (primary_baseline - primary_child) / primary_baseline if primary_baseline else None,
            "strict_primary_mae_improvement": strict_improvement,
        },
        "interpretation": "development_measurement_only; no_selection_or_promotion; no_automatic_sol_dispatch",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inspect", action="store_true")
    parser.add_argument("--split-manifest", type=Path, required=True)
    parser.add_argument("--hanna-csv", type=Path, required=True)
    parser.add_argument("--successor-contract", type=Path, required=True)
    args = parser.parse_args(argv)
    if not args.inspect:
        parser.error("only provider-free --inspect is available from the CLI")
    schedule(split_manifest=args.split_manifest, hanna_csv=args.hanna_csv, successor_contract=args.successor_contract)
    print(canonical({"study_id": STUDY_ID, "cells": 26, "items": 13, "groups": 7, "provider_calls_made": 0, "process_launches": 0}).decode("utf-8"), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
