"""Frozen remaining-TRAIN Grok expansion for unchanged baseline and child20."""
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
from types import ModuleType, SimpleNamespace
from typing import Any

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
STUDY_ID = "hbq-human-alignment-optimizer-v13-train-expansion-v1"
CONTRACT_PATH = HERE / "study-contract.json"
V11 = REPO / "evaluation-results/hbq-human-alignment-optimizer-v11-child20-train-screen-v1/study.py"
V11_SHA256 = "af2d326934f51ddb83b6449a760295f46921c87189c653558de37930af018f11"
V11_COMMIT = "dc7b59a"
RECONCILE = REPO / "evaluation-results/hbq-human-alignment-optimizer-v10-fresh96-confirmation-grok-reconcile-v1/reconcile.py"
RECONCILE_SHA256 = "6c132ade2b95bad54a580736e9e8b66fef4cb8b9733f91c0398dd35e4488293d"
RECONCILE_COMMIT = "c7d9191"
SPLIT_SHA256 = "6ffa942b595449f4118c2cd51f3a36716126612a7c10f4765953c17eb1efdbc2"
CSV_SHA256 = "ef59054d27fa32def06cfdc57243b1dd09c7e71f40b6d9d43fecfbf60e59026b"
SUCCESSOR_SHA256 = "b0f6dd24415c388a3104f8c9304ce301193cf0a48631a86c4886bc8ce48468e7"
BASELINE = "candidate-102cc7f06c9a99a7"
CHILD20 = "broader-nextwave-20-missing_evidence_not_no-referent-evidence"
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
    value = strict(CONTRACT_PATH.read_bytes(), "study contract")
    expected = {
        "analysis_rule": {"coverage": "include_every_finite_numeric_score_even_when_coverage_is_false", "primary": "absolute_error_per_item_then_mean_within_each_prompt_group_then_equal_mean_across_22_prompt_groups"},
        "authority": {"confirmation_access": "forbidden_in_this_study", "confirmation_cells": 0, "development_only": True, "dspy_optuna_runtime": False, "previous_results": "unchanged", "promotion": "none", "selection": "none", "sol_execution": "unopened"},
        "format_version": 1,
        "geometry": {"candidates": 2, "grok_cells": 88, "grok_max_concurrent_cells": 10, "sol_cells": 0, "train_groups": 22, "train_items": 44},
        "kind": "remaining_train_expansion_matched_child20_panel",
        "requested_judge": {"endpoint": "grok_primary", "model": "grok-4.6", "provider_attested": False, "reasoning": "high", "reported_model": "grok-4.6-build", "tools": "off"},
        "study_id": STUDY_ID,
    }
    if value != expected:
        raise ValueError("study contract drifted")
    return value


def source_items(*, split_manifest: Path, hanna_csv: Path, successor_contract: Path) -> list[dict[str, Any]]:
    split_raw, csv_raw, successor_raw = Path(split_manifest).read_bytes(), Path(hanna_csv).read_bytes(), Path(successor_contract).read_bytes()
    if sha256(split_raw) != SPLIT_SHA256 or sha256(csv_raw) != CSV_SHA256 or sha256(successor_raw) != SUCCESSOR_SHA256:
        raise ValueError("frozen TRAIN source pin drifted")
    split = json.loads(split_raw.decode("utf-8"))
    train = [(row.get("prompt_group_id"), row.get("item_id")) for row in split.get("items", []) if row.get("partition") == "train"]
    if len(train) != 48 or len(set(train)) != 48 or any(not isinstance(group, str) or not isinstance(item, str) for group, item in train) or len({group for group, _item in train}) != 24:
        raise ValueError("frozen TRAIN split geometry drifted")
    v11 = load(V11, V11_COMMIT, V11_SHA256, "_v13_v11")
    retained = {item: group for group, item in train if item not in set(v11.PAIRS.values())}
    if len(retained) != 44 or len(set(retained.values())) != 22:
        raise ValueError("remaining TRAIN geometry drifted")
    v1 = v11.load(v11.V1, v11.V1_COMMIT, v11.V1_SHA256, "_v13_v1")
    aliases = {row["item_id"]: row for row in v1.derive_eligible_map(Path(successor_contract), Path(hanna_csv)) if row.get("item_id") in retained}
    if set(aliases) != set(retained) or any(aliases[item].get("prompt_group_id") != group for item, group in retained.items()):
        raise ValueError("pinned source alias map drifted")
    rows = list(csv.DictReader(io.StringIO(csv_raw.decode("utf-8-sig"))))
    selected: list[dict[str, Any]] = []
    for item_id, group in retained.items():
        alias = aliases[item_id]
        matches = [row for row in rows if row["Story ID"] == alias["story_id"] and row["Model"] == alias["source_model"] and "prompt-" + hashlib.sha256(row["Prompt"].encode()).hexdigest()[:16] == group]
        stories = {row["Story"] for row in matches}
        if len(matches) != 3 or len(stories) != 1 or any(row["Model"] == "Human" for row in matches):
            raise ValueError("frozen TRAIN item source drifted")
        prompt, story, model, story_id = matches[0]["Prompt"], matches[0]["Story"], matches[0]["Model"], matches[0]["Story ID"]
        selected.append({"item_id": item_id, "prompt_group_id": group, "partition": "train", "prompt": prompt, "story": story, "target": {dimension: sum(float(row[dimension]) for row in matches) / 3 for dimension in DIMS}, "source_binding_sha256": sha256({"prompt_group_id": group, "story_id": story_id, "model": model, "prompt": prompt, "story": story})})
    return sorted(selected, key=lambda item: (item["prompt_group_id"], item["item_id"]))


def schedule(*, split_manifest: Path, hanna_csv: Path, successor_contract: Path) -> dict[str, Any]:
    contract_value = contract(); v11 = load(V11, V11_COMMIT, V11_SHA256, "_v13_schedule_v11")
    v10 = v11.load(v11.V10, v11.V10_COMMIT, v11.V10_SHA256, "_v13_v10")
    validation = v10._module(v10.VALIDATION, v10.VALIDATION_SHA256, "_v13_validation")
    panel = [row for row in v10._panel(validation) if row["candidate_id"] in {BASELINE, CHILD20}]
    if len(panel) != 2 or [row["candidate_id"] for row in panel] != [BASELINE, CHILD20]:
        raise ValueError("V10 paired candidate panel drifted")
    items = source_items(split_manifest=split_manifest, hanna_csv=hanna_csv, successor_contract=successor_contract)
    cells: list[dict[str, Any]] = []
    for item in items:
        for candidate in panel:
            payload = v10._payload(validation, item, candidate)
            cells.append({"cell_id": "v13-train-" + sha256({"candidate": candidate["candidate_id"], "item": item["item_id"]})[:20], "ordinal": len(cells) + 1, "candidate_id": candidate["candidate_id"], "candidate_sha256": candidate["candidate_sha256"], "candidate_instruction_sha256": candidate["instruction_sha256"], "candidate_profile_sha256": candidate["profile_sha256"], "item_id": item["item_id"], "prompt_group_id": item["prompt_group_id"], "partition": "train", "source_binding_sha256": item["source_binding_sha256"], "target": item["target"], "target_sha256": sha256(item["target"]), "payload_base64": base64.b64encode(payload).decode("ascii"), "payload_sha256": sha256(payload), "endpoint_payload_sha256s": {"grok_primary": sha256(payload), "sol_later": sha256(payload)}})
    if len(cells) != 88 or len({row["cell_id"] for row in cells}) != 88:
        raise ValueError("V13 cell geometry drifted")
    value: dict[str, Any] = {"format_version": 1, "study_id": STUDY_ID, "kind": contract_value["kind"], "endpoint": "grok_primary", "requested_judge": contract_value["requested_judge"], "groups": [{"prompt_group_id": group, "partition": "train"} for group in sorted({item["prompt_group_id"] for item in items})], "cells": cells, "geometry": contract_value["geometry"], "analysis_rule": contract_value["analysis_rule"], "authority": contract_value["authority"], "source": {"split_manifest_sha256": SPLIT_SHA256, "hanna_csv_sha256": CSV_SHA256, "successor_contract_sha256": SUCCESSOR_SHA256}}
    value["schedule_sha256"] = sha256(value)
    return value


def _known_payloads(schedule_value: Mapping[str, Any]) -> set[bytes]:
    cells = schedule_value.get("cells")
    if not isinstance(cells, list) or len(cells) != 88:
        raise ValueError("V13 schedule payload geometry drifted")
    payloads: set[bytes] = set()
    for row in cells:
        if not isinstance(row, Mapping) or not isinstance(row.get("payload_base64"), str) or not isinstance(row.get("payload_sha256"), str):
            raise ValueError("V13 schedule payload binding drifted")
        try:
            raw = base64.b64decode(row["payload_base64"], validate=True)
        except ValueError as error:
            raise ValueError("V13 schedule payload encoding drifted") from error
        if sha256(raw) != row["payload_sha256"]:
            raise ValueError("V13 schedule payload digest drifted")
        writing = strict(raw, "frozen V13 outbound payload").get("writing")
        if not isinstance(writing, Mapping) or set(writing) != {"prompt", "story"} or any(not isinstance(writing[name], str) for name in writing):
            raise ValueError("V13 schedule payload wrapper drifted")
        payloads.add(raw)
    if len(payloads) != len(cells):
        raise ValueError("V13 schedule payload uniqueness drifted")
    return payloads


@contextmanager
def bound(*, schedule_value: Mapping[str, Any]) -> Iterator[tuple[ModuleType, ModuleType, ModuleType, ModuleType]]:
    v11 = load(V11, V11_COMMIT, V11_SHA256, "_v13_bound_v11")
    with v11.bound(schedule_value=schedule_value) as (lifecycle, runtime, v9):
        known_payloads, original_study, original_precontact = _known_payloads(schedule_value), lifecycle.STUDY_ID, v9._validate_precontact_payload

        def exact_precontact(payload: bytes) -> None:
            if type(payload) is not bytes or payload not in known_payloads:
                raise ValueError("outbound payload is not an exact frozen V13 payload")

        lifecycle.STUDY_ID, v9._validate_precontact_payload = STUDY_ID, exact_precontact
        try:
            yield lifecycle, runtime, v9, v11
        finally:
            lifecycle.STUDY_ID, v9._validate_precontact_payload = original_study, original_precontact


def prepare_all(*, output_root: Path, queue_root: Path, authorization_acknowledgement_sha256: str, split_manifest: Path, hanna_csv: Path, successor_contract: Path, route_provider: Callable[[Path], tuple[dict[str, Any], dict[str, Any]]]) -> dict[str, Any]:
    value = schedule(split_manifest=split_manifest, hanna_csv=hanna_csv, successor_contract=successor_contract)
    with bound(schedule_value=value) as (lifecycle, runtime, v9, _v11):
        result = lifecycle.prepare_all(output_root=Path(output_root), queue_root=Path(queue_root), authorization_acknowledgement_sha256=authorization_acknowledgement_sha256, route_provider=v9._validated_route(v9.parent_stack(), runtime, Path(queue_root), route_provider), normalized_root=Path(output_root).parent / ".v13-normalized", materialization_root=Path(output_root).parent / ".v13-materialization", frozen_successor_path=Path(output_root).parent / ".v13-successor.json", hanna_csv_path=Path(output_root).parent / ".v13-source.csv")
    prepared = result.get("prepared_cells", []); expected = {row["cell_id"] for row in value["cells"]}
    if len(prepared) != 88 or set(prepared) != expected or (Path(output_root) / "schedule.json").read_bytes() != canonical(value):
        raise ValueError("lower lifecycle did not prepare exactly 88 cells")
    return {"study_id": STUDY_ID, "prepared_cells": prepared, "logical_cells": 88, "provider_calls_made": 0, "process_launches": 0}


def _response(helper: ModuleType, raw: bytes, route: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    envelope = helper.strict(raw, "native response", canonical_required=False); reported = route.get("reported_model")
    if (set(envelope) != helper.RESPONSE_FIELDS or envelope.get("stopReason") != "end_turn" or envelope.get("num_turns") != 1 or not isinstance(envelope.get("requestId"), str) or not envelope["requestId"] or not isinstance(envelope.get("sessionId"), str) or not envelope["sessionId"] or not isinstance(reported, str)):
        raise ValueError("native response identity or terminal state drifted")
    structured = envelope.get("structuredOutput")
    if not isinstance(envelope.get("text"), str) or not isinstance(structured, Mapping) or helper.strict(envelope["text"].encode("utf-8"), "native response text", canonical_required=False) != structured:
        raise ValueError("native response text/schema disagreement")
    scores, evidence, coverage = structured.get("scores"), structured.get("evidence"), structured.get("coverage")
    if set(structured) != {"scores", "evidence", "coverage"} or not all(isinstance(value, Mapping) and set(value) == set(DIMS) for value in (scores, evidence, coverage)):
        raise ValueError("native response dimension schema drifted")
    for dimension in DIMS:
        if type(scores[dimension]) not in {int, float} or not math.isfinite(float(scores[dimension])) or not 0 <= float(scores[dimension]) <= 5 or not isinstance(evidence[dimension], str) or type(coverage[dimension]) is not bool:
            raise ValueError("native response score, evidence, or coverage drifted")
    usage = envelope.get("usage"); usage_keys = {"input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens", "reasoning_tokens", "total_tokens"}
    if not isinstance(usage, Mapping) or set(usage) != usage_keys or any(type(usage[key]) is not int or usage[key] < 0 for key in usage_keys) or usage["input_tokens"] <= 0 or usage["output_tokens"] <= 0 or usage["total_tokens"] < max(usage["input_tokens"], usage["output_tokens"]):
        raise ValueError("native response usage telemetry drifted")
    model_usage = envelope.get("modelUsage"); model_keys = {"inputTokens", "outputTokens", "cacheReadInputTokens", "cacheCreationInputTokens", "modelCalls", "costUSD"}
    if not isinstance(model_usage, Mapping) or set(model_usage) != {reported} or not isinstance(model_usage[reported], Mapping) or set(model_usage[reported]) != model_keys or model_usage[reported].get("modelCalls") != 1:
        raise ValueError("native response model usage drifted")
    model = model_usage[reported]
    if any(type(model[key]) is not int or model[key] < 0 for key in model_keys - {"costUSD"}) or model["inputTokens"] <= 0 or model["outputTokens"] <= 0:
        raise ValueError("native response model call telemetry drifted")
    cost, ticks = helper._nonnegative_number(envelope.get("total_cost_usd"), "cost"), envelope.get("total_cost_usd_ticks")
    if type(ticks) is not int or ticks < 0 or ticks != round(cost * 10_000_000_000) or not math.isclose(helper._nonnegative_number(model["costUSD"], "model cost"), cost, rel_tol=0, abs_tol=1e-12):
        raise ValueError("native response cost telemetry drifted")
    thought = envelope.get("thought")
    if not isinstance(thought, str):
        raise ValueError("native response thought telemetry drifted")
    return dict(envelope), {"provider": "xai", "requested_model": route.get("model"), "reported_model": reported, "request_id": envelope["requestId"], "session_id": envelope["sessionId"], "native_endpoint_contact_cardinality": "unproven", "tools_enabled": False}


def _execute(value: Mapping[str, Any], output_root: Path, queue_root: Path, authorization_acknowledgement_sha256: str, cell_id: str, route_provider: Callable[[Path], tuple[dict[str, Any], dict[str, Any]]], runner: Callable[..., Mapping[str, Any]] | None) -> dict[str, Any]:
    with bound(schedule_value=value) as (lifecycle, runtime, v9, v11):
        old = load(RECONCILE, RECONCILE_COMMIT, RECONCILE_SHA256, "_v13_response_helper")
        selected = v9.parent_stack()._guard_runner(runner or lifecycle.live()._default_runner, lifecycle, value)
        return v11._execute_bound(value=value, lifecycle=lifecycle, runtime=runtime, v9=v9, reconciler=SimpleNamespace(_response=_response), response_helper=old.helper(), selected=selected, output_root=Path(output_root), queue_root=Path(queue_root), authorization_acknowledgement_sha256=authorization_acknowledgement_sha256, cell_id=cell_id, route_provider=v9._validated_route(v9.parent_stack(), runtime, Path(queue_root), route_provider))


def execute_one(*, output_root: Path, queue_root: Path, authorization_acknowledgement_sha256: str, split_manifest: Path, hanna_csv: Path, successor_contract: Path, cell_id: str, allow_remote: bool, route_provider: Callable[[Path], tuple[dict[str, Any], dict[str, Any]]], runner: Callable[..., Mapping[str, Any]] | None = None) -> dict[str, Any]:
    if allow_remote is not True:
        raise ValueError("explicit allow_remote required")
    return _execute(schedule(split_manifest=split_manifest, hanna_csv=hanna_csv, successor_contract=successor_contract), Path(output_root), Path(queue_root), authorization_acknowledgement_sha256, cell_id, route_provider, runner)


def execute_wave(*, output_root: Path, queue_root: Path, authorization_acknowledgement_sha256: str, split_manifest: Path, hanna_csv: Path, successor_contract: Path, allow_remote: bool, route_provider: Callable[[Path], tuple[dict[str, Any], dict[str, Any]]], runner: Callable[..., Mapping[str, Any]] | None = None) -> list[dict[str, Any]]:
    if allow_remote is not True:
        raise ValueError("explicit allow_remote required")
    value = schedule(split_manifest=split_manifest, hanna_csv=hanna_csv, successor_contract=successor_contract)
    with bound(schedule_value=value) as (lifecycle, runtime, v9, v11):
        old = load(RECONCILE, RECONCILE_COMMIT, RECONCILE_SHA256, "_v13_wave_helper")
        selected = v9.parent_stack()._guard_runner(runner or lifecycle.live()._default_runner, lifecycle, value)
        async def launch() -> list[dict[str, Any]]:
            route, evidence = v9._validated_route(v9.parent_stack(), runtime, Path(queue_root), route_provider)(Path(queue_root)); gate = asyncio.Semaphore(10)
            async def one(cell_id: str) -> dict[str, Any]:
                async with gate:
                    return await asyncio.to_thread(v11._execute_bound, value=value, lifecycle=lifecycle, runtime=runtime, v9=v9, reconciler=SimpleNamespace(_response=_response), response_helper=old.helper(), selected=selected, output_root=Path(output_root), queue_root=Path(queue_root), authorization_acknowledgement_sha256=authorization_acknowledgement_sha256, cell_id=cell_id, route_provider=lambda _ignored: (route, evidence))
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


def report(*, output_root: Path, authorization_acknowledgement_sha256: str, split_manifest: Path, hanna_csv: Path, successor_contract: Path) -> dict[str, Any]:
    value = schedule(split_manifest=split_manifest, hanna_csv=hanna_csv, successor_contract=successor_contract); roots = Path(output_root); expected = {row["cell_id"] for row in value["cells"]}
    if not roots.is_dir() or {path.name for path in roots.iterdir()} != {"schedule.json", ".claims", *expected} or (roots / "schedule.json").read_bytes() != canonical(value):
        raise ValueError("incomplete or ambiguous V13 receipt inventory")
    old = load(RECONCILE, RECONCILE_COMMIT, RECONCILE_SHA256, "_v13_report_helper"); helper = old.helper(); cells: list[dict[str, Any]] = []
    grouped: dict[str, dict[str, list[dict[str, Any]]]] = {BASELINE: {}, CHILD20: {}}; request_ids: set[str] = set(); session_ids: set[str] = set()
    expected_items = {group["prompt_group_id"]: {row["item_id"] for row in value["cells"] if row["prompt_group_id"] == group["prompt_group_id"]} for group in value["groups"]}
    with bound(schedule_value=value) as (lifecycle, _runtime, v9, _v11):
        source = lifecycle.live(); parent = v9.parent_stack(); v9._validate_claims(roots, expected); frozen_route: Mapping[str, Any] | None = None; frozen_evidence: Mapping[str, Any] | None = None
        for row in value["cells"]:
            root = roots / row["cell_id"]; stored = v9.strict(v9.stable(root / "prepared.json"), "prepared"); acknowledgement = v9.strict(v9.stable(root / "authorization-acknowledgement.json"), "acknowledgement")
            if acknowledgement.get("acknowledgement_sha256") != authorization_acknowledgement_sha256:
                raise ValueError("receipt acknowledgement drifted")
            route, evidence = stored.get("route"), stored.get("route_evidence")
            if not isinstance(route, Mapping) or not isinstance(evidence, Mapping):
                raise TypeError("ambiguous receipt route or evidence")
            if frozen_route is None: frozen_route, frozen_evidence = route, evidence
            elif route != frozen_route or evidence != frozen_evidence: raise ValueError("mixed receipt route or evidence")
            raw, prompt, schema = lifecycle.payload(row); request, response, identity, _settings = lifecycle.admit(root, row, value, raw, prompt, schema, route, evidence, authorization_acknowledgement_sha256, source)
            envelope, _identity = _response(helper, response, route); structured = envelope["structuredOutput"]; scores, coverage = structured["scores"], structured["coverage"]
            request_id, session_id = identity.get("request_id") if isinstance(identity, Mapping) else None, identity.get("session_id") if isinstance(identity, Mapping) else None
            if not isinstance(request_id, str) or not request_id or request_id in request_ids or not isinstance(session_id, str) or not session_id or session_id in session_ids:
                raise ValueError("duplicate or invalid native identity")
            request_ids.add(request_id); session_ids.add(session_id)
            cell = {"cell_id": row["cell_id"], "candidate_id": row["candidate_id"], "item_id": row["item_id"], "prompt_group_id": row["prompt_group_id"], "partition": "train", "payload_sha256": row["payload_sha256"], "native_request_sha256": sha256(request), "native_response_sha256": sha256(response), "scores": {dimension: float(scores[dimension]) for dimension in DIMS}, "coverage": {dimension: coverage[dimension] for dimension in DIMS}, "target": {dimension: float(row["target"][dimension]) for dimension in DIMS}}
            cell["per_item_mae"] = _mean([abs(cell["scores"][dimension] - cell["target"][dimension]) for dimension in DIMS]); grouped[row["candidate_id"]].setdefault(row["prompt_group_id"], []).append(cell); cells.append(cell)
        if frozen_route is None or frozen_evidence is None: raise ValueError("missing V13 route evidence")
        lifecycle.validate_frozen_route(frozen_route, frozen_evidence); parent._validate_route_evidence(frozen_route, frozen_evidence)
    if len(cells) != 88 or len(request_ids) != 88 or len(session_ids) != 88: raise ValueError("incomplete V13 receipt projection")
    metrics: list[dict[str, Any]] = []
    for candidate in (BASELINE, CHILD20):
        by_group = grouped[candidate]
        if set(by_group) != set(expected_items) or any({row["item_id"] for row in by_group[group]} != expected_items[group] or len(by_group[group]) != len(expected_items[group]) for group in expected_items): raise ValueError("candidate TRAIN grouping drifted")
        group_mae = {group: _mean([row["per_item_mae"] for row in by_group[group]]) for group in sorted(by_group)}
        metrics.append({"candidate_id": candidate, "per_group_mean_item_mae": group_mae, "equal_group_mean_item_mae": _mean(list(group_mae.values())), "item_count": 44, "group_count": 22})
    baseline, child = metrics; primary_baseline, primary_child = baseline["equal_group_mean_item_mae"], child["equal_group_mean_item_mae"]
    return {"format_version": 1, "study_id": STUDY_ID, "kind": "receipt_derived_88_cell_grok_train_expansion_report", "endpoint": "grok_primary", "authority": contract()["authority"], "analysis_rule": contract()["analysis_rule"], "native_endpoint_contact_cardinality": "unproven", "cells": cells, "unique_request_ids": len(request_ids), "unique_session_ids": len(session_ids), "metrics": metrics, "comparison": {"baseline_candidate_id": BASELINE, "child_candidate_id": CHILD20, "child20_minus_baseline": primary_child - primary_baseline, "relative_reduction": (primary_baseline - primary_child) / primary_baseline if primary_baseline else None, "strict_primary_mae_improvement": primary_child < primary_baseline}, "interpretation": "development_measurement_only; no_selection_or_promotion; no_automatic_sol_dispatch"}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument("--inspect", action="store_true"); parser.add_argument("--split-manifest", type=Path, required=True); parser.add_argument("--hanna-csv", type=Path, required=True); parser.add_argument("--successor-contract", type=Path, required=True)
    args = parser.parse_args(argv)
    if not args.inspect: parser.error("only provider-free --inspect is available from the CLI")
    value = schedule(split_manifest=args.split_manifest, hanna_csv=args.hanna_csv, successor_contract=args.successor_contract)
    print(canonical({"study_id": STUDY_ID, "cells": len(value["cells"]), "items": 44, "groups": 22, "provider_calls_made": 0, "process_launches": 0}).decode(), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
