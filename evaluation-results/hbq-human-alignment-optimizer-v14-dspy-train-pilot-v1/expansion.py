"""Fresh remaining-TRAIN Grok screen: child20 versus recovered DSPy descendant."""
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
STUDY_ID = "hbq-human-alignment-optimizer-v14-dspy-train-expansion-v1"
CONTRACT_PATH = HERE / "expansion-contract.json"
V13 = REPO / "evaluation-results/hbq-human-alignment-optimizer-v13-train-expansion-v1/study.py"
V13_SHA256 = "f2b5a4c178cf2a7919b5dfd8c5ddde7bf5c1e0e9aa81a2f2f4d0bdd9b97c8261"
V13_COMMIT = "9c76e81"
PILOT = REPO / "evaluation-results/hbq-human-alignment-optimizer-v14-dspy-train-pilot-v1/study.py"
PILOT_SHA256 = "4446c2b3e1472039b2aa0c607cfe84656aa5504d3fe37ae428945a1f7b62fc3f"
PILOT_COMMIT = "f28db1b"
PILOT_CONTRACT = PILOT.parent / "study-contract.json"
PILOT_CONTRACT_SHA256 = "d92013a659f494547053d2737459a7715247894b113f60669b2fdf761ff2e8b3"
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
    raw = path.read_bytes()
    blob = subprocess.run(["git", "-C", str(REPO), "show", f"{commit}:{path.relative_to(REPO).as_posix()}"], capture_output=True, check=False)
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
    if path.read_bytes() != raw:
        raise ValueError("pinned module changed during load")
    return module


def contract() -> dict[str, Any]:
    value = strict(CONTRACT_PATH.read_bytes(), "expansion contract")
    expected = {
        "analysis_rule": {"coverage": "include_every_finite_numeric_score_even_when_coverage_is_false", "primary": "absolute_error_per_item_then_mean_within_each_prompt_group_then_equal_mean_across_22_prompt_groups"},
        "authority": {"confirmation": "none", "development_in_sample_only": True, "endpoint_pooling": "forbidden", "generalization": "none", "previous_v13": "unchanged_not_adopted", "promotion": "none", "runtime": "none", "selection": "none", "sol": "separate_endpoint_package"},
        "format_version": 1,
        "geometry": {"candidates": 2, "grok_cells": 88, "groups": 22, "items": 44, "max_concurrency": 10, "sol_cells": 0},
        "kind": "fresh_dspy_descendant_child20_remaining_train_expansion",
        "pilot_pins": {"study_sha256": PILOT_SHA256, "study_contract_sha256": PILOT_CONTRACT_SHA256},
        "study_id": STUDY_ID,
    }
    if value != expected:
        raise ValueError("expansion contract drifted")
    return value


def _pilot() -> ModuleType:
    pilot = load(PILOT, PILOT_COMMIT, PILOT_SHA256, "_v14_expansion_pilot")
    raw = PILOT_CONTRACT.read_bytes()
    blob = subprocess.run(["git", "-C", str(REPO), "show", f"{PILOT_COMMIT}:{PILOT_CONTRACT.relative_to(REPO).as_posix()}"], capture_output=True, check=False)
    if sha256(raw) != PILOT_CONTRACT_SHA256 or blob.returncode or blob.stdout != raw:
        raise ValueError("pinned pilot contract drifted")
    return pilot


@contextmanager
def _adapted(value: Mapping[str, Any]) -> Iterator[ModuleType]:
    v13 = load(V13, V13_COMMIT, V13_SHA256, "_v14_expansion_v13")
    contract_value = contract()
    originals = {name: getattr(v13, name) for name in ("schedule", "contract", "STUDY_ID", "BASELINE", "CHILD20")}
    v13.schedule = lambda **_kwargs: dict(value)
    v13.contract = lambda: dict(contract_value)
    v13.STUDY_ID, v13.BASELINE, v13.CHILD20 = STUDY_ID, CHILD20, DESCENDANT
    try:
        yield v13
    finally:
        for name, original in originals.items():
            setattr(v13, name, original)


def schedule(*, split_manifest: Path, hanna_csv: Path, successor_contract: Path, recovered_descendant: Path) -> dict[str, Any]:
    contract_value = contract(); pilot = _pilot(); v13 = load(V13, V13_COMMIT, V13_SHA256, "_v14_expansion_schedule_v13")
    v11 = v13.load(v13.V11, v13.V11_COMMIT, v13.V11_SHA256, "_v14_expansion_v11")
    v10 = v11.load(v11.V10, v11.V10_COMMIT, v11.V10_SHA256, "_v14_expansion_v10")
    validation = v10._module(v10.VALIDATION, v10.VALIDATION_SHA256, "_v14_expansion_validation")
    child = next((row for row in v10._panel(validation) if row["candidate_id"] == CHILD20), None)
    if child is None:
        raise ValueError("pinned child20 candidate is absent")
    descendant = pilot._recovered_candidate(Path(recovered_descendant))
    if child.get("profile_raw") != descendant["profile_raw"] or child.get("profile_sha256") != descendant["profile_sha256"]:
        raise ValueError("descendant profile is not byte-identical to child20")
    expected_parent = {"candidate_id": CHILD20, "candidate_sha256": child["candidate_sha256"], "instruction_sha256": child["instruction_sha256"], "profile_sha256": child["profile_sha256"]}
    if descendant["parent"] != expected_parent:
        raise ValueError("recovered descendant parent binding drifted")
    items = v13.source_items(split_manifest=Path(split_manifest), hanna_csv=Path(hanna_csv), successor_contract=Path(successor_contract))
    cells: list[dict[str, Any]] = []
    for item in items:
        for candidate in (child, descendant):
            payload = v10._payload(validation, item, candidate)
            cells.append({"cell_id": "v14-expansion-" + sha256({"candidate": candidate["candidate_id"], "item": item["item_id"]})[:20], "ordinal": len(cells) + 1, "candidate_id": candidate["candidate_id"], "candidate_sha256": candidate["candidate_sha256"], "candidate_instruction_sha256": candidate["instruction_sha256"], "candidate_profile_sha256": candidate["profile_sha256"], "item_id": item["item_id"], "prompt_group_id": item["prompt_group_id"], "partition": "train", "source_binding_sha256": item["source_binding_sha256"], "target": item["target"], "target_sha256": sha256(item["target"]), "payload_base64": base64.b64encode(payload).decode("ascii"), "payload_sha256": sha256(payload), "endpoint_payload_sha256s": {"grok_primary": sha256(payload), "sol_later": sha256(payload)}})
    if len(items) != 44 or len({item["prompt_group_id"] for item in items}) != 22 or len(cells) != 88 or len({row["cell_id"] for row in cells}) != 88:
        raise ValueError("V14 expansion geometry drifted")
    value: dict[str, Any] = {"format_version": 1, "study_id": STUDY_ID, "kind": contract_value["kind"], "endpoint": "grok_primary", "groups": [{"prompt_group_id": group, "partition": "train"} for group in sorted({item["prompt_group_id"] for item in items})], "cells": cells, "geometry": contract_value["geometry"], "analysis_rule": contract_value["analysis_rule"], "authority": contract_value["authority"], "source": {"v13_study_sha256": V13_SHA256, "pilot_study_sha256": PILOT_SHA256, "pilot_contract_sha256": PILOT_CONTRACT_SHA256, "split_manifest_sha256": v13.SPLIT_SHA256, "hanna_csv_sha256": v13.CSV_SHA256, "successor_contract_sha256": v13.SUCCESSOR_SHA256, "recovered_descendant_sha256": pilot.RECOVERED_SHA256}}
    value["schedule_sha256"] = sha256(value)
    return value


@contextmanager
def bound(*, schedule_value: Mapping[str, Any]) -> Iterator[tuple[ModuleType, ModuleType, ModuleType, ModuleType, ModuleType]]:
    with _adapted(schedule_value) as v13, v13.bound(schedule_value=schedule_value) as (lifecycle, runtime, v9, v11):
        yield lifecycle, runtime, v9, v11, v13


def prepare_all(*, output_root: Path, queue_root: Path, authorization_acknowledgement_sha256: str, split_manifest: Path, hanna_csv: Path, successor_contract: Path, recovered_descendant: Path, route_provider: Callable[[Path], tuple[dict[str, Any], dict[str, Any]]]) -> dict[str, Any]:
    value = schedule(split_manifest=split_manifest, hanna_csv=hanna_csv, successor_contract=successor_contract, recovered_descendant=recovered_descendant)
    pilot = _pilot()
    with bound(schedule_value=value) as (lifecycle, runtime, v9, _v11, _v13):
        pilot._disjoint_actual_sources(lifecycle, output_root=Path(output_root), queue_root=Path(queue_root), split_manifest=Path(split_manifest), hanna_csv=Path(hanna_csv), successor_contract=Path(successor_contract), recovered_descendant=Path(recovered_descendant))
        result = lifecycle.prepare_all(output_root=Path(output_root), queue_root=Path(queue_root), authorization_acknowledgement_sha256=authorization_acknowledgement_sha256, route_provider=v9._validated_route(v9.parent_stack(), runtime, Path(queue_root), route_provider), normalized_root=Path(output_root).parent / ".v14-expansion-normalized", materialization_root=Path(output_root).parent / ".v14-expansion-materialization", frozen_successor_path=Path(output_root).parent / ".v14-expansion-successor.json", hanna_csv_path=Path(output_root).parent / ".v14-expansion-source.csv")
    prepared, expected = result.get("prepared_cells", []), {row["cell_id"] for row in value["cells"]}
    if len(prepared) != 88 or set(prepared) != expected or (Path(output_root) / "schedule.json").read_bytes() != canonical(value):
        raise ValueError("lower lifecycle did not prepare exactly 88 V14 expansion cells")
    return {"study_id": STUDY_ID, "prepared_cells": prepared, "logical_cells": 88, "provider_calls_made": 0, "process_launches": 0}


def execute_wave(*, output_root: Path, queue_root: Path, authorization_acknowledgement_sha256: str, split_manifest: Path, hanna_csv: Path, successor_contract: Path, recovered_descendant: Path, allow_remote: bool, route_provider: Callable[[Path], tuple[dict[str, Any], dict[str, Any]]], runner: Callable[..., Mapping[str, Any]] | None = None) -> list[dict[str, Any]]:
    if allow_remote is not True:
        raise ValueError("explicit allow_remote required")
    value = schedule(split_manifest=split_manifest, hanna_csv=hanna_csv, successor_contract=successor_contract, recovered_descendant=recovered_descendant)
    pilot = _pilot()
    with bound(schedule_value=value) as (lifecycle, runtime, v9, v11, v13):
        pilot._disjoint_actual_sources(lifecycle, output_root=Path(output_root), queue_root=Path(queue_root), split_manifest=Path(split_manifest), hanna_csv=Path(hanna_csv), successor_contract=Path(successor_contract), recovered_descendant=Path(recovered_descendant))
        old = v11.load(v11.RECONCILE, v11.RECONCILE_COMMIT, v11.RECONCILE_SHA256, "_v14_expansion_response_helper")
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


def report(*, output_root: Path, authorization_acknowledgement_sha256: str, split_manifest: Path, hanna_csv: Path, successor_contract: Path, recovered_descendant: Path) -> dict[str, Any]:
    value = schedule(split_manifest=split_manifest, hanna_csv=hanna_csv, successor_contract=successor_contract, recovered_descendant=recovered_descendant)
    with _adapted(value) as v13:
        result = v13.report(output_root=Path(output_root), authorization_acknowledgement_sha256=authorization_acknowledgement_sha256, split_manifest=Path(split_manifest), hanna_csv=Path(hanna_csv), successor_contract=Path(successor_contract))
    comparison = result["comparison"]
    result["kind"] = "receipt_derived_88_cell_grok_dspy_child20_train_expansion_report"
    result["comparison"] = {"child20_candidate_id": comparison["baseline_candidate_id"], "descendant_candidate_id": comparison["child_candidate_id"], "descendant_minus_child20": comparison["child20_minus_baseline"], "relative_reduction": comparison["relative_reduction"], "strict_primary_mae_improvement": comparison["strict_primary_mae_improvement"]}
    result["interpretation"] = "development_in_sample_screen_only; no_selection_or_promotion_or_generalization; no_automatic_sol_dispatch"
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument("--inspect", action="store_true"); parser.add_argument("--split-manifest", type=Path, required=True); parser.add_argument("--hanna-csv", type=Path, required=True); parser.add_argument("--successor-contract", type=Path, required=True); parser.add_argument("--recovered-descendant", type=Path, required=True)
    args = parser.parse_args(argv)
    if not args.inspect: parser.error("only provider-free --inspect is available from the CLI")
    value = schedule(split_manifest=args.split_manifest, hanna_csv=args.hanna_csv, successor_contract=args.successor_contract, recovered_descendant=args.recovered_descendant)
    print(canonical({"study_id": STUDY_ID, "cells": len(value["cells"]), "items": 44, "groups": 22, "provider_calls_made": 0, "process_launches": 0}).decode(), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
