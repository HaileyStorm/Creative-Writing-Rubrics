"""Minimal paired child20 TRAIN screen composed from the lower Grok lifecycle."""
from __future__ import annotations

import argparse
import asyncio
import base64
import csv
import hashlib
import importlib.util
import io
import json
import subprocess
import sys
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path
from types import ModuleType
from typing import Any

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
STUDY_ID = "hbq-human-alignment-optimizer-v11-child20-train-screen-v1"
V10 = REPO / "evaluation-results/hbq-human-alignment-optimizer-v10-fresh96-confirmation-candidates-v1/study.py"
V10_SHA256 = "38ea9c9c0cf96dfc0ca32b64ee6639515600bc01b93e204cdd397bae393b2a6f"
V10_COMMIT = "1c10bae"
V9 = REPO / "evaluation-results/hbq-human-alignment-optimizer-v9-desc18-broad-replication-grok-exec-v1/executor.py"
V9_SHA256 = "d719d484fabc12110fe36f61c379edf8d15aa701f97f025d1ff2ac24f1d2f4a4"
V9_COMMIT = "4d3b2ef"
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
PAIRS = {
    "prompt-489dbd34451e1ce7": "item-09006dab15b970e6",
    "prompt-624948bf9021d60a": "item-f0124faa5a62734e",
    "prompt-6b7fff0c3794370c": "item-b5161cbf50b87beb",
    "prompt-91868234f35c72d9": "item-8c65749a245496a2",
}
SOURCE_ALIASES = {
    "item-09006dab15b970e6": {"story_id": "925", "source_model": "HINT"},
    "item-f0124faa5a62734e": {"story_id": "403", "source_model": "GPT-2 (tag)"},
    "item-b5161cbf50b87beb": {"story_id": "594", "source_model": "RoBERTa"},
    "item-8c65749a245496a2": {"story_id": "225", "source_model": "CTRL"},
}


def canonical(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode()


def sha256(value: bytes | Any) -> str:
    return hashlib.sha256(value if isinstance(value, bytes) else canonical(value)).hexdigest()


def strict(raw: bytes, label: str) -> dict[str, Any]:
    value = json.loads(raw.decode("utf-8"), parse_constant=lambda token: (_ for _ in ()).throw(ValueError(token)))
    if not isinstance(value, dict) or canonical(value) != raw:
        raise ValueError(f"invalid {label}")
    return value


def pinned(path: Path, commit: str, digest: str) -> bytes:
    raw = path.read_bytes()
    relative = path.relative_to(REPO).as_posix()
    blob = subprocess.run(["git", "-C", str(REPO), "show", f"{commit}:{relative}"], capture_output=True, check=False)
    if blob.returncode or sha256(raw) != digest or blob.stdout != raw:
        raise ValueError("pinned dependency drifted")
    return raw


def load(path: Path, commit: str, digest: str, name: str) -> ModuleType:
    raw = pinned(path, commit, digest)
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


def source_items(*, split_manifest: Path, hanna_csv: Path, successor_contract: Path) -> list[dict[str, Any]]:
    split_raw, csv_raw, successor_raw = Path(split_manifest).read_bytes(), Path(hanna_csv).read_bytes(), Path(successor_contract).read_bytes()
    if sha256(split_raw) != SPLIT_SHA256 or sha256(csv_raw) != CSV_SHA256 or sha256(successor_raw) != SUCCESSOR_SHA256:
        raise ValueError("frozen TRAIN source pin drifted")
    split = json.loads(split_raw.decode("utf-8"))
    if not all({"partition": "train", "prompt_group_id": group} in split.get("groups", []) and {"partition": "train", "prompt_group_id": group, "item_id": item} in split.get("items", []) for group, item in PAIRS.items()):
        raise ValueError("TRAIN pair is absent from frozen split")
    v1 = load(V1, V1_COMMIT, V1_SHA256, "_v11_v1_source")
    aliases = {
        row["item_id"]: row
        for row in v1.derive_eligible_map(Path(successor_contract), Path(hanna_csv))
        if row.get("item_id") in set(PAIRS.values())
    }
    if len(aliases) != 4 or any(aliases.get(item, {}).get("prompt_group_id") != group for group, item in PAIRS.items()):
        raise ValueError("pinned source alias map drifted")
    if any({key: aliases[item].get(key) for key in ("story_id", "source_model")} != SOURCE_ALIASES[item] for item in PAIRS.values()):
        raise ValueError("pinned source aliases drifted")
    rows = list(csv.DictReader(io.StringIO(csv_raw.decode("utf-8-sig"))))
    selected: list[dict[str, Any]] = []
    for group, item_id in PAIRS.items():
        alias = aliases[item_id]
        matches = [row for row in rows if row["Story ID"] == alias["story_id"] and row["Model"] == alias["source_model"] and "prompt-" + hashlib.sha256(row["Prompt"].encode()).hexdigest()[:16] == group]
        stories = {row["Story"] for row in matches}
        if len(matches) != 3 or len(stories) != 1 or any(row["Model"] == "Human" for row in matches):
            raise ValueError("frozen TRAIN item source drifted")
        target = {name: sum(float(row[name]) for row in matches) / 3 for name in DIMS}
        prompt, story, model, story_id = matches[0]["Prompt"], matches[0]["Story"], matches[0]["Model"], matches[0]["Story ID"]
        selected.append({"item_id": item_id, "prompt_group_id": group, "partition": "train", "prompt": prompt, "story": story, "target": target, "source_binding_sha256": sha256({"prompt_group_id": group, "story_id": story_id, "model": model, "prompt": prompt, "story": story})})
    return sorted(selected, key=lambda item: item["prompt_group_id"])


def schedule(*, split_manifest: Path, hanna_csv: Path, successor_contract: Path) -> dict[str, Any]:
    v10 = load(V10, V10_COMMIT, V10_SHA256, "_v11_v10")
    validation = v10._module(v10.VALIDATION, v10.VALIDATION_SHA256, "_v11_validation")
    panel = [row for row in v10._panel(validation) if row["candidate_id"] in {BASELINE, CHILD20}]
    if len(panel) != 2:
        raise ValueError("V10 paired panel drifted")
    cells = []
    for item in source_items(split_manifest=split_manifest, hanna_csv=hanna_csv, successor_contract=successor_contract):
        for candidate in panel:
            payload = v10._payload(validation, item, candidate)
            cells.append({"cell_id": "v11-train-" + sha256({"candidate": candidate["candidate_id"], "item": item["item_id"]})[:20], "candidate_id": candidate["candidate_id"], "candidate_sha256": candidate["candidate_sha256"], "candidate_instruction_sha256": candidate["instruction_sha256"], "candidate_profile_sha256": candidate["profile_sha256"], "item_id": item["item_id"], "prompt_group_id": item["prompt_group_id"], "partition": "train", "source_binding_sha256": item["source_binding_sha256"], "target": item["target"], "target_sha256": sha256(item["target"]), "payload_base64": base64.b64encode(payload).decode(), "payload_sha256": sha256(payload), "endpoint_payload_sha256s": {"grok_primary": sha256(payload), "sol_later": sha256(payload)}})
    if len(cells) != 8 or len({cell["cell_id"] for cell in cells}) != 8 or any(cell["partition"] != "train" for cell in cells):
        raise ValueError("V11 cell geometry drifted")
    value = {"format_version": 1, "study_id": STUDY_ID, "kind": "paired_child20_train_screen_schedule", "groups": [{"prompt_group_id": group, "partition": "train"} for group in sorted(PAIRS)], "cells": cells, "authority": "development_only", "confirmation": {"status": "unopened", "cells": 0}, "source": {"split_manifest_sha256": SPLIT_SHA256, "hanna_csv_sha256": CSV_SHA256, "successor_contract_sha256": SUCCESSOR_SHA256}}
    value["schedule_sha256"] = sha256(value)
    return value


@contextmanager
def bound(*, schedule_value: Mapping[str, Any]) -> Iterator[tuple[ModuleType, ModuleType, ModuleType]]:
    v9 = load(V9, V9_COMMIT, V9_SHA256, "_v11_v9")
    parent = v9.parent_stack(); base = parent.desc13_stack(); runtime = base.v3_runtime()._runtime(); lifecycle = runtime.lifecycle(); source = lifecycle.live()
    original_schedule, original_study = lifecycle.schedule, lifecycle.STUDY_ID
    lifecycle.schedule, lifecycle.STUDY_ID = (lambda **_kwargs: (source, dict(schedule_value))), STUDY_ID
    try:
        yield lifecycle, runtime, v9
    finally:
        lifecycle.schedule, lifecycle.STUDY_ID = original_schedule, original_study


def prepare_all(*, output_root: Path, queue_root: Path, authorization_acknowledgement_sha256: str, split_manifest: Path, hanna_csv: Path, successor_contract: Path, route_provider: Callable[[Path], tuple[dict[str, Any], dict[str, Any]]]) -> dict[str, Any]:
    value = schedule(split_manifest=split_manifest, hanna_csv=hanna_csv, successor_contract=successor_contract)
    with bound(schedule_value=value) as (lifecycle, runtime, v9):
        result = lifecycle.prepare_all(output_root=Path(output_root), queue_root=Path(queue_root), authorization_acknowledgement_sha256=authorization_acknowledgement_sha256, route_provider=v9._validated_route(v9.parent_stack(), runtime, Path(queue_root), route_provider), normalized_root=Path(output_root).parent / ".v11-normalized", materialization_root=Path(output_root).parent / ".v11-materialization", frozen_successor_path=Path(output_root).parent / ".v11-successor.json", hanna_csv_path=Path(output_root).parent / ".v11-source.csv")
    prepared = result.get("prepared_cells", [])
    if len(prepared) != 8 or set(prepared) != {row["cell_id"] for row in value["cells"]} or (Path(output_root) / "schedule.json").read_bytes() != canonical(value):
        raise ValueError("lower lifecycle did not prepare exactly eight cells")
    return {"study_id": STUDY_ID, "prepared_cells": prepared, "logical_cells": 8, "provider_calls_made": 0, "process_launches": 0}


def _execute_bound(*, value: Mapping[str, Any], lifecycle: ModuleType, runtime: ModuleType, v9: ModuleType, reconciler: ModuleType, response_helper: ModuleType, selected: Callable[..., Mapping[str, Any]], output_root: Path, queue_root: Path, authorization_acknowledgement_sha256: str, cell_id: str, route_provider: Callable[[Path], tuple[dict[str, Any], dict[str, Any]]]) -> dict[str, Any]:
    if cell_id not in {row["cell_id"] for row in value["cells"]}:
        raise ValueError("unknown V11 cell")
    slot = record = None
    try:
        slot, record = runtime._acquire_global_slot(Path(output_root), cell_id)
        if runtime._claim(Path(output_root), cell_id) != "claimed_now":
            raise ValueError("no resend or concurrent cell claim")
        def checked(**kwargs: Any) -> Mapping[str, Any]:
            before = kwargs["before_contact"]

            def precontact() -> None:
                v9._validate_precontact_payload(kwargs["prompt"])
                v9._require_contact_validity(kwargs["route"])
                before()

            result = selected(**{**kwargs, "before_contact": precontact})
            response = result.get("native_response_bytes") if isinstance(result, Mapping) else None
            if not isinstance(response, bytes):
                raise TypeError("runner response bytes are absent")
            reconciler._response(response_helper, response, kwargs["route"])
            return result

        return lifecycle.execute_one(output_root=Path(output_root), queue_root=Path(queue_root), authorization_acknowledgement_sha256=authorization_acknowledgement_sha256, cell_id=cell_id, allow_remote=True, route_provider=route_provider, runner=checked, normalized_root=Path(output_root).parent / ".v11-normalized", materialization_root=Path(output_root).parent / ".v11-materialization", frozen_successor_path=Path(output_root).parent / ".v11-successor.json", hanna_csv_path=Path(output_root).parent / ".v11-source.csv")
    finally:
        runtime._release_global_slot(slot, record)


def _execute_with_schedule(*, value: Mapping[str, Any], output_root: Path, queue_root: Path, authorization_acknowledgement_sha256: str, cell_id: str, route_provider: Callable[[Path], tuple[dict[str, Any], dict[str, Any]]], runner: Callable[..., Mapping[str, Any]] | None) -> dict[str, Any]:
    with bound(schedule_value=value) as (lifecycle, runtime, v9):
        reconciler = load(RECONCILE, RECONCILE_COMMIT, RECONCILE_SHA256, "_v11_response_reconcile")
        parent = v9.parent_stack()
        selected = parent._guard_runner(runner or lifecycle.live()._default_runner, lifecycle, value)
        validated = v9._validated_route(parent, runtime, Path(queue_root), route_provider)
        return _execute_bound(value=value, lifecycle=lifecycle, runtime=runtime, v9=v9, reconciler=reconciler, response_helper=reconciler.helper(), selected=selected, output_root=output_root, queue_root=queue_root, authorization_acknowledgement_sha256=authorization_acknowledgement_sha256, cell_id=cell_id, route_provider=validated)


def execute_one(*, output_root: Path, queue_root: Path, authorization_acknowledgement_sha256: str, split_manifest: Path, hanna_csv: Path, successor_contract: Path, cell_id: str, allow_remote: bool, route_provider: Callable[[Path], tuple[dict[str, Any], dict[str, Any]]], runner: Callable[..., Mapping[str, Any]] | None = None) -> dict[str, Any]:
    if allow_remote is not True:
        raise ValueError("explicit allow_remote required")
    value = schedule(split_manifest=split_manifest, hanna_csv=hanna_csv, successor_contract=successor_contract)
    return _execute_with_schedule(value=value, output_root=Path(output_root), queue_root=Path(queue_root), authorization_acknowledgement_sha256=authorization_acknowledgement_sha256, cell_id=cell_id, route_provider=route_provider, runner=runner)


def execute_eight(*, output_root: Path, queue_root: Path, authorization_acknowledgement_sha256: str, split_manifest: Path, hanna_csv: Path, successor_contract: Path, allow_remote: bool, route_provider: Callable[[Path], tuple[dict[str, Any], dict[str, Any]]], runner: Callable[..., Mapping[str, Any]] | None = None) -> list[dict[str, Any]]:
    if allow_remote is not True:
        raise ValueError("explicit allow_remote required")
    value = schedule(split_manifest=split_manifest, hanna_csv=hanna_csv, successor_contract=successor_contract)
    with bound(schedule_value=value) as (lifecycle, runtime, v9):
        reconciler = load(RECONCILE, RECONCILE_COMMIT, RECONCILE_SHA256, "_v11_response_reconcile")
        response_helper = reconciler.helper()
        parent = v9.parent_stack()
        selected = parent._guard_runner(runner or lifecycle.live()._default_runner, lifecycle, value)

        async def launch() -> list[dict[str, Any]]:
            validated = v9._validated_route(v9.parent_stack(), runtime, Path(queue_root), route_provider)
            route, evidence = validated(Path(queue_root))
            gate = asyncio.Semaphore(8)

            async def one(cell_id: str) -> dict[str, Any]:
                async with gate:
                    return await asyncio.to_thread(_execute_bound, value=value, lifecycle=lifecycle, runtime=runtime, v9=v9, reconciler=reconciler, response_helper=response_helper, selected=selected, output_root=Path(output_root), queue_root=Path(queue_root), authorization_acknowledgement_sha256=authorization_acknowledgement_sha256, cell_id=cell_id, route_provider=lambda _ignored: (route, evidence))

            completed = await asyncio.gather(*(one(row["cell_id"]) for row in value["cells"]), return_exceptions=True)
            failure = next((item for item in completed if isinstance(item, BaseException)), None)
            if failure is not None:
                raise failure
            return [item for item in completed if isinstance(item, dict)]

        return asyncio.run(launch())


def report(*, output_root: Path, authorization_acknowledgement_sha256: str, split_manifest: Path, hanna_csv: Path, successor_contract: Path) -> dict[str, Any]:
    value = schedule(split_manifest=split_manifest, hanna_csv=hanna_csv, successor_contract=successor_contract)
    roots = Path(output_root)
    expected = {row["cell_id"] for row in value["cells"]}
    if not roots.is_dir() or {path.name for path in roots.iterdir()} != {"schedule.json", ".claims", *expected} or (roots / "schedule.json").read_bytes() != canonical(value):
        raise ValueError("incomplete or ambiguous V11 receipt inventory")
    reconciler = load(RECONCILE, RECONCILE_COMMIT, RECONCILE_SHA256, "_v11_report_reconcile")
    helper = reconciler.helper()
    groups: dict[str, dict[str, float]] = {BASELINE: {}, CHILD20: {}}
    cells: list[dict[str, Any]] = []
    request_ids: set[str] = set()
    session_ids: set[str] = set()
    with bound(schedule_value=value) as (lifecycle, _runtime, v9):
        source = lifecycle.live()
        parent = v9.parent_stack()
        frozen_route: Mapping[str, Any] | None = None
        frozen_evidence: Mapping[str, Any] | None = None
        for row in value["cells"]:
            root = roots / row["cell_id"]
            stored = v9.strict(v9.stable(root / "prepared.json"), "prepared")
            acknowledgement = v9.strict(v9.stable(root / "authorization-acknowledgement.json"), "acknowledgement")
            if acknowledgement.get("acknowledgement_sha256") != authorization_acknowledgement_sha256:
                raise ValueError("receipt acknowledgement drifted")
            if not isinstance(stored.get("route"), Mapping):
                raise TypeError("ambiguous receipt route")
            if not isinstance(stored.get("route_evidence"), Mapping):
                raise TypeError("ambiguous receipt route evidence")
            if frozen_route is None:
                frozen_route, frozen_evidence = stored["route"], stored["route_evidence"]
            elif stored["route"] != frozen_route or stored["route_evidence"] != frozen_evidence:
                raise ValueError("mixed receipt route or evidence")
            raw, prompt, schema = lifecycle.payload(row)
            request, response, identity, _settings = lifecycle.admit(root, row, value, raw, prompt, schema, stored["route"], stored["route_evidence"], authorization_acknowledgement_sha256, source)
            envelope, _identity = reconciler._response(helper, response, stored["route"])
            request_id = identity.get("request_id") if isinstance(identity, Mapping) else None
            session_id = identity.get("session_id") if isinstance(identity, Mapping) else None
            if (not isinstance(request_id, str) or not request_id or not isinstance(session_id, str) or not session_id
                    or request_id in request_ids or session_id in session_ids):
                raise ValueError("duplicate or invalid native identity")
            request_ids.add(request_id); session_ids.add(session_id)
            scores = envelope["structuredOutput"]["scores"]
            if set(scores) != set(DIMS) or any(type(scores[dimension]) not in {int, float} for dimension in DIMS):
                raise ValueError("native score schema drifted")
            mae = sum(abs(float(scores[dimension]) - float(row["target"][dimension])) for dimension in DIMS) / len(DIMS)
            candidate_groups = groups.get(row["candidate_id"])
            if candidate_groups is None or row["prompt_group_id"] in candidate_groups or row["partition"] != "train":
                raise ValueError("ambiguous candidate or TRAIN grouping")
            candidate_groups[row["prompt_group_id"]] = mae
            cells.append({"cell_id": row["cell_id"], "candidate_id": row["candidate_id"], "prompt_group_id": row["prompt_group_id"], "partition": "train", "native_request_sha256": sha256(request), "native_response_sha256": sha256(response), "scores": {dimension: float(scores[dimension]) for dimension in DIMS}, "target": dict(row["target"]), "mae": mae})
    if (frozen_route is None or frozen_evidence is None or len(cells) != len(expected)
            or len(request_ids) != len(expected) or len(session_ids) != len(expected)
            or any(set(by_group) != set(PAIRS) for by_group in groups.values())):
        raise ValueError("incomplete V11 receipt projection")
    lifecycle.validate_frozen_route(frozen_route, frozen_evidence)
    parent._validate_route_evidence(frozen_route, frozen_evidence)
    metrics = []
    for candidate in (BASELINE, CHILD20):
        group_mae = dict(sorted(groups[candidate].items()))
        metrics.append({"candidate_id": candidate, "equal_group_mae": sum(group_mae.values()) / len(group_mae), "group_mae": group_mae})
    baseline, child = metrics
    strict = child["equal_group_mae"] < baseline["equal_group_mae"]
    return {"format_version": 1, "study_id": STUDY_ID, "kind": "receipt_derived_8_cell_grok_train_screen_report", "endpoint": "grok_primary", "partition": "train", "native_endpoint_contact_cardinality": "unproven", "cells": cells, "unique_request_ids": len(request_ids), "unique_session_ids": len(session_ids), "metrics": metrics, "comparison": {"baseline_candidate_id": BASELINE, "child_candidate_id": CHILD20, "child20_minus_baseline": child["equal_group_mae"] - baseline["equal_group_mae"], "relative_reduction": (baseline["equal_group_mae"] - child["equal_group_mae"]) / baseline["equal_group_mae"] if baseline["equal_group_mae"] else None, "strict_mean_mae_improvement": strict}, "later_matched_sol8_gate": {"sole_gate": "strict_child20_mean_mae_improvement", "satisfied": strict, "effect": "may_open_later_separately_gated_matched_sol8_measurement_only", "promotion": "none", "sol_execution": "unopened"}}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument("--inspect", action="store_true"); parser.add_argument("--split-manifest", type=Path, required=True); parser.add_argument("--hanna-csv", type=Path, required=True); parser.add_argument("--successor-contract", type=Path, required=True)
    args = parser.parse_args(argv)
    if not args.inspect:
        parser.error("only provider-free --inspect is available from the CLI")
    value = schedule(split_manifest=args.split_manifest, hanna_csv=args.hanna_csv, successor_contract=args.successor_contract)
    print(canonical({"study_id": STUDY_ID, "cells": len(value["cells"]), "items": 4, "groups": 4, "provider_calls_made": 0, "process_launches": 0}).decode(), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
