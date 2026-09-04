"""Fresh V12-development Grok measurement: child20 versus recovered DSPy."""
from __future__ import annotations

import argparse
import asyncio
import base64
import hashlib
import importlib.util
import json
import subprocess
import sys
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
STUDY_ID = "hbq-human-alignment-optimizer-v14-dspy-development-panel-v1"
CONTRACT_PATH = HERE / "development-contract.json"
V12 = REPO / "evaluation-results/hbq-human-alignment-optimizer-v12-development-panel-v1/study.py"
V12_SHA256, V12_COMMIT = "a1100bc16528287571d1b7198729124a705990ab7561385d271df27a7e2b7851", "10d4251"
V13 = REPO / "evaluation-results/hbq-human-alignment-optimizer-v13-train-expansion-v1/study.py"
V13_SHA256, V13_COMMIT = "f2b5a4c178cf2a7919b5dfd8c5ddde7bf5c1e0e9aa81a2f2f4d0bdd9b97c8261", "9c76e81"
PILOT = HERE / "study.py"
PILOT_SHA256, PILOT_COMMIT = "4446c2b3e1472039b2aa0c607cfe84656aa5504d3fe37ae428945a1f7b62fc3f", "f28db1b"
CHILD20 = "broader-nextwave-20-missing_evidence_not_no-referent-evidence"
DESCENDANT = "candidate-62195a3b90edd96d"
DIMS = ("Relevance", "Coherence", "Empathy", "Surprise", "Engagement", "Complexity")


def canonical(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode()


def sha256(value: bytes | Any) -> str:
    return hashlib.sha256(value if isinstance(value, bytes) else canonical(value)).hexdigest()


def strict(raw: bytes, label: str) -> dict[str, Any]:
    value = json.loads(raw.decode("utf-8"), parse_constant=lambda token: (_ for _ in ()).throw(ValueError(token)))
    if not isinstance(value, dict) or canonical(value) != raw:
        raise ValueError(f"invalid {label}")
    return value


def load(path: Path, commit: str, digest: str, name: str) -> ModuleType:
    raw = Path(path).read_bytes()
    blob = subprocess.run(["git", "-C", str(REPO), "show", f"{commit}:{Path(path).relative_to(REPO).as_posix()}"], capture_output=True, check=False)
    if blob.returncode or sha256(raw) != digest or blob.stdout != raw:
        raise ValueError("pinned dependency drifted")
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ValueError("pinned module cannot load")
    module = importlib.util.module_from_spec(spec); sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(name, None)
    if Path(path).read_bytes() != raw:
        raise ValueError("pinned module changed during load")
    return module


def contract() -> dict[str, Any]:
    value = strict(CONTRACT_PATH.read_bytes(), "development contract")
    expected = {
        "analysis_rule": {"coverage": "include_every_finite_numeric_score_even_when_coverage_is_false", "primary": "absolute_error_per_item_then_mean_within_each_prompt_group_then_equal_mean_across_7_prompt_groups", "rank_correlations": {"group_mean_7": "Spearman of per-group mean model score versus per-group mean human target, per dimension", "item_13": "Spearman of item model score versus item human target, per dimension"}},
        "authority": {"confirmation": "none", "development_in_sample_only": True, "endpoint_pooling": "forbidden", "generalization": "none", "previous_v12": "unchanged_not_adopted", "promotion": "none", "runtime": "none", "selection": "none", "sol": "separate_endpoint_package"},
        "format_version": 1,
        "geometry": {"candidates": 2, "grok_cells": 26, "groups": 7, "items": 13, "max_concurrency": 10, "sol_cells": 0},
        "kind": "fresh_dspy_descendant_child20_development_panel",
        "pins": {"v12_study_sha256": V12_SHA256, "v13_study_sha256": V13_SHA256, "v14_pilot_study_sha256": PILOT_SHA256},
        "requested_judge": {"endpoint": "grok_primary", "model": "grok-4.6", "provider_attested": False, "reasoning": "high", "reported_model": "grok-4.6-build", "tools": "off"},
        "study_id": STUDY_ID,
    }
    if value != expected:
        raise ValueError("development contract drifted")
    return value


def _pilot() -> ModuleType:
    return load(PILOT, PILOT_COMMIT, PILOT_SHA256, "_v14_development_pilot")


def schedule(*, split_manifest: Path, hanna_csv: Path, successor_contract: Path, recovered_descendant: Path) -> dict[str, Any]:
    contract_value, v12, pilot = contract(), load(V12, V12_COMMIT, V12_SHA256, "_v14_development_v12"), _pilot()
    v10 = v12.load(v12.V10, v12.V10_COMMIT, v12.V10_SHA256, "_v14_development_v10")
    validation = v10._module(v10.VALIDATION, v10.VALIDATION_SHA256, "_v14_development_validation")
    child = next((row for row in v10._panel(validation) if row["candidate_id"] == CHILD20), None)
    if child is None:
        raise ValueError("pinned child20 candidate is absent")
    descendant = pilot._recovered_candidate(Path(recovered_descendant))
    expected_parent = {"candidate_id": CHILD20, "candidate_sha256": child["candidate_sha256"], "instruction_sha256": child["instruction_sha256"], "profile_sha256": child["profile_sha256"]}
    if child.get("profile_raw") != descendant["profile_raw"] or child.get("profile_sha256") != descendant["profile_sha256"] or descendant["parent"] != expected_parent:
        raise ValueError("recovered descendant parent binding drifted")
    items = v12.source_items(split_manifest=Path(split_manifest), hanna_csv=Path(hanna_csv), successor_contract=Path(successor_contract))
    cells: list[dict[str, Any]] = []
    for item in items:
        for candidate in (child, descendant):
            payload = v10._payload(validation, item, candidate)
            cells.append({"cell_id": "v14-development-" + sha256({"candidate": candidate["candidate_id"], "item": item["item_id"]})[:20], "ordinal": len(cells) + 1, "candidate_id": candidate["candidate_id"], "candidate_sha256": candidate["candidate_sha256"], "candidate_instruction_sha256": candidate["instruction_sha256"], "candidate_profile_sha256": candidate["profile_sha256"], "item_id": item["item_id"], "prompt_group_id": item["prompt_group_id"], "partition": "development", "source_binding_sha256": item["source_binding_sha256"], "target": item["target"], "target_sha256": sha256(item["target"]), "payload_base64": base64.b64encode(payload).decode("ascii"), "payload_sha256": sha256(payload), "endpoint_payload_sha256s": {"grok_primary": sha256(payload), "sol_later": sha256(payload)}})
    if len(items) != 13 or len({item["prompt_group_id"] for item in items}) != 7 or len(cells) != 26 or len({row["cell_id"] for row in cells}) != 26:
        raise ValueError("V14 development geometry drifted")
    value: dict[str, Any] = {"format_version": 1, "study_id": STUDY_ID, "kind": contract_value["kind"], "endpoint": "grok_primary", "requested_judge": contract_value["requested_judge"], "groups": [{"prompt_group_id": group, "partition": "development"} for group in sorted({item["prompt_group_id"] for item in items})], "cells": cells, "geometry": contract_value["geometry"], "analysis_rule": contract_value["analysis_rule"], "authority": contract_value["authority"], "source": {"v12_study_sha256": V12_SHA256, "v13_study_sha256": V13_SHA256, "v14_pilot_study_sha256": PILOT_SHA256, "split_manifest_sha256": v12.SPLIT_SHA256, "hanna_csv_sha256": v12.CSV_SHA256, "successor_contract_sha256": v12.SUCCESSOR_SHA256, "recovered_descendant_sha256": pilot.RECOVERED_SHA256}}
    value["schedule_sha256"] = sha256(value)
    return value


@contextmanager
def bound(*, schedule_value: Mapping[str, Any]) -> Iterator[tuple[ModuleType, ModuleType, ModuleType, ModuleType, ModuleType]]:
    v13 = load(V13, V13_COMMIT, V13_SHA256, "_v14_development_v13")
    original_id, original_payloads = v13.STUDY_ID, v13._known_payloads

    def exact_payloads(value: Mapping[str, Any]) -> set[bytes]:
        cells = value.get("cells")
        if not isinstance(cells, list) or len(cells) != 26:
            raise ValueError("V14 development schedule payload geometry drifted")
        payloads: set[bytes] = set()
        for row in cells:
            if not isinstance(row, Mapping) or not isinstance(row.get("payload_base64"), str) or not isinstance(row.get("payload_sha256"), str):
                raise TypeError("V14 development schedule payload binding type drifted")
            try:
                raw = base64.b64decode(row["payload_base64"], validate=True)
            except ValueError as error:
                raise ValueError("V14 development schedule payload encoding drifted") from error
            if v13.sha256(raw) != row["payload_sha256"]:
                raise ValueError("V14 development schedule payload digest drifted")
            writing = v13.strict(raw, "frozen V14 development outbound payload").get("writing")
            if not isinstance(writing, Mapping) or set(writing) != {"prompt", "story"} or any(not isinstance(writing[name], str) for name in writing):
                raise ValueError("V14 development schedule payload wrapper drifted")
            payloads.add(raw)
        if len(payloads) != len(cells):
            raise ValueError("V14 development schedule payload uniqueness drifted")
        return payloads

    v13.STUDY_ID, v13._known_payloads = STUDY_ID, exact_payloads
    try:
        with v13.bound(schedule_value=schedule_value) as (lifecycle, runtime, v9, v11):
            yield lifecycle, runtime, v9, v11, v13
    finally:
        v13.STUDY_ID, v13._known_payloads = original_id, original_payloads


def _disjoint(pilot: ModuleType, lifecycle: ModuleType, *, output_root: Path, queue_root: Path, split_manifest: Path, hanna_csv: Path, successor_contract: Path, recovered_descendant: Path) -> None:
    pilot._disjoint_actual_sources(lifecycle, output_root=Path(output_root), queue_root=Path(queue_root), split_manifest=Path(split_manifest), hanna_csv=Path(hanna_csv), successor_contract=Path(successor_contract), recovered_descendant=Path(recovered_descendant))


def prepare_all(*, output_root: Path, queue_root: Path, authorization_acknowledgement_sha256: str, split_manifest: Path, hanna_csv: Path, successor_contract: Path, recovered_descendant: Path, route_provider: Callable[[Path], tuple[dict[str, Any], dict[str, Any]]] | None = None) -> dict[str, Any]:
    value, pilot = schedule(split_manifest=split_manifest, hanna_csv=hanna_csv, successor_contract=successor_contract, recovered_descendant=recovered_descendant), _pilot()
    with bound(schedule_value=value) as (lifecycle, runtime, v9, _v11, _v13):
        _disjoint(pilot, lifecycle, output_root=output_root, queue_root=queue_root, split_manifest=split_manifest, hanna_csv=hanna_csv, successor_contract=successor_contract, recovered_descendant=recovered_descendant)
        result = lifecycle.prepare_all(output_root=Path(output_root), queue_root=Path(queue_root), authorization_acknowledgement_sha256=authorization_acknowledgement_sha256, route_provider=v9._validated_route(v9.parent_stack(), runtime, Path(queue_root), route_provider), normalized_root=Path(output_root).parent / ".v14-development-normalized", materialization_root=Path(output_root).parent / ".v14-development-materialization", frozen_successor_path=Path(output_root).parent / ".v14-development-successor.json", hanna_csv_path=Path(output_root).parent / ".v14-development-source.csv")
    prepared, expected = result.get("prepared_cells", []), {row["cell_id"] for row in value["cells"]}
    if len(prepared) != 26 or set(prepared) != expected or (Path(output_root) / "schedule.json").read_bytes() != canonical(value):
        raise ValueError("lower lifecycle did not prepare exactly 26 V14 development cells")
    return {"study_id": STUDY_ID, "prepared_cells": prepared, "logical_cells": 26, "provider_calls_made": 0, "process_launches": 0}


def execute_wave(*, output_root: Path, queue_root: Path, authorization_acknowledgement_sha256: str, split_manifest: Path, hanna_csv: Path, successor_contract: Path, recovered_descendant: Path, allow_remote: bool, route_provider: Callable[[Path], tuple[dict[str, Any], dict[str, Any]]] | None = None, runner: Callable[..., Mapping[str, Any]] | None = None) -> list[dict[str, Any]]:
    if allow_remote is not True:
        raise ValueError("explicit allow_remote required")
    value, pilot = schedule(split_manifest=split_manifest, hanna_csv=hanna_csv, successor_contract=successor_contract, recovered_descendant=recovered_descendant), _pilot()
    with bound(schedule_value=value) as (lifecycle, runtime, v9, v11, v13):
        _disjoint(pilot, lifecycle, output_root=output_root, queue_root=queue_root, split_manifest=split_manifest, hanna_csv=hanna_csv, successor_contract=successor_contract, recovered_descendant=recovered_descendant)
        old = v11.load(v11.RECONCILE, v11.RECONCILE_COMMIT, v11.RECONCILE_SHA256, "_v14_development_response_helper")
        selected = v9.parent_stack()._guard_runner(runner or lifecycle.live()._default_runner, lifecycle, value)

        async def launch() -> list[dict[str, Any]]:
            route, evidence = v9._validated_route(v9.parent_stack(), runtime, Path(queue_root), route_provider)(Path(queue_root)); gate = asyncio.Semaphore(10)

            async def one(cell_id: str) -> dict[str, Any]:
                async with gate:
                    return await asyncio.to_thread(v11._execute_bound, value=value, lifecycle=lifecycle, runtime=runtime, v9=v9, reconciler=SimpleNamespace(_response=v13._response), response_helper=old.helper(), selected=selected, output_root=Path(output_root), queue_root=Path(queue_root), authorization_acknowledgement_sha256=authorization_acknowledgement_sha256, cell_id=cell_id, route_provider=lambda _ignored: (route, evidence))

            outcomes = await asyncio.gather(*(one(row["cell_id"]) for row in value["cells"]), return_exceptions=True)
            failure = next((outcome for outcome in outcomes if isinstance(outcome, BaseException)), None)
            if failure is not None:
                raise failure
            return [outcome for outcome in outcomes if isinstance(outcome, dict)]

        return asyncio.run(launch())


@contextmanager
def _report_adapter(value: Mapping[str, Any]) -> Iterator[ModuleType]:
    v12, v13 = load(V12, V12_COMMIT, V12_SHA256, "_v14_development_report_v12"), load(V13, V13_COMMIT, V13_SHA256, "_v14_development_report_v13")
    original_load, original_schedule, original_contract = v12.load, v12.schedule, v12.contract
    original_id, original_baseline, original_child = v12.STUDY_ID, v12.BASELINE, v12.CHILD20
    reconciler = original_load(v12.RECONCILE, v12.RECONCILE_COMMIT, v12.RECONCILE_SHA256, "_v14_development_report_helper")

    def adapted_load(path: Path, commit: str, digest: str, name: str) -> ModuleType | SimpleNamespace:
        if path == v12.RECONCILE:
            return SimpleNamespace(helper=reconciler.helper, _response=v13._response)
        return original_load(path, commit, digest, name)

    v12.load, v12.schedule, v12.contract = adapted_load, lambda **_kwargs: dict(value), lambda: contract()
    v12.STUDY_ID, v12.BASELINE, v12.CHILD20 = STUDY_ID, CHILD20, DESCENDANT
    try:
        yield v12
    finally:
        v12.load, v12.schedule, v12.contract = original_load, original_schedule, original_contract
        v12.STUDY_ID, v12.BASELINE, v12.CHILD20 = original_id, original_baseline, original_child


def report(*, output_root: Path, authorization_acknowledgement_sha256: str, split_manifest: Path, hanna_csv: Path, successor_contract: Path, recovered_descendant: Path) -> dict[str, Any]:
    value = schedule(split_manifest=split_manifest, hanna_csv=hanna_csv, successor_contract=successor_contract, recovered_descendant=recovered_descendant)
    with _report_adapter(value) as v12:
        result = v12.report(output_root=Path(output_root), authorization_acknowledgement_sha256=authorization_acknowledgement_sha256, split_manifest=Path(split_manifest), hanna_csv=Path(hanna_csv), successor_contract=Path(successor_contract))
    comparison = result["comparison"]
    result["kind"] = "receipt_derived_26_cell_grok_dspy_child20_development_report"
    result["comparison"] = {"child20_candidate_id": comparison["baseline_candidate_id"], "descendant_candidate_id": comparison["child_candidate_id"], "descendant_minus_child20": comparison["child20_minus_baseline"], "relative_reduction": comparison["relative_reduction"], "strict_primary_mae_improvement": comparison["strict_primary_mae_improvement"]}
    result["interpretation"] = "development_in_sample_screen_only; no_selection_or_promotion_or_generalization; no_automatic_sol_dispatch"
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument("--inspect", action="store_true"); parser.add_argument("--split-manifest", type=Path, required=True); parser.add_argument("--hanna-csv", type=Path, required=True); parser.add_argument("--successor-contract", type=Path, required=True); parser.add_argument("--recovered-descendant", type=Path, required=True)
    args = parser.parse_args(argv)
    if not args.inspect:
        parser.error("only provider-free --inspect is available from the CLI")
    value = schedule(split_manifest=args.split_manifest, hanna_csv=args.hanna_csv, successor_contract=args.successor_contract, recovered_descendant=args.recovered_descendant)
    print(canonical({"study_id": STUDY_ID, "cells": len(value["cells"]), "items": 13, "groups": 7, "provider_calls_made": 0, "process_launches": 0}).decode(), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
