"""Fresh eight-cell TRAIN-only Grok screen: child20 versus a recovered DSPy descendant."""
from __future__ import annotations

import argparse
import asyncio
import base64
import hashlib
import importlib.util
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
STUDY_ID = "hbq-human-alignment-optimizer-v14-dspy-train-pilot-v1"
CONTRACT_PATH = HERE / "study-contract.json"
V11 = REPO / "evaluation-results/hbq-human-alignment-optimizer-v11-child20-train-screen-v1/study.py"
V11_SHA256 = "af2d326934f51ddb83b6449a760295f46921c87189c653558de37930af018f11"
V11_COMMIT = "dc7b59a"
V13 = REPO / "evaluation-results/hbq-human-alignment-optimizer-v13-train-expansion-v1/study.py"
V13_SHA256 = "f2b5a4c178cf2a7919b5dfd8c5ddde7bf5c1e0e9aa81a2f2f4d0bdd9b97c8261"
RECONCILE = REPO / "evaluation-results/hbq-human-alignment-optimizer-v10-fresh96-confirmation-grok-reconcile-v1/reconcile.py"
RECONCILE_SHA256 = "6c132ade2b95bad54a580736e9e8b66fef4cb8b9733f91c0398dd35e4488293d"
RECONCILE_COMMIT = "c7d9191"
RECOVERED = Path(r"C:\Users\Haile\Documents\cwr-hanna-dspy-proposal-recovery-cbe403dd-20260904-r1\recovered-descendant.json")
RECOVERED_SHA256 = "2a4dcf87b0c79d2371995f7c30c81a9f4d948b2252fcc6c80963c6e037b79e59"
CHILD20 = "broader-nextwave-20-missing_evidence_not_no-referent-evidence"
DESCENDANT = "candidate-62195a3b90edd96d"
DESCENDANT_SHA256 = "62195a3b90edd96d619279b5e229f78862b971ba44d10de86468dee6badbe9e4"
DESCENDANT_INSTRUCTION_SHA256 = "a62778cd4ad4612bb8efc6ac3ec82e49da7dc0c933c4c70f086d51304cdf957c"
DESCENDANT_PROFILE_SHA256 = "07cd3652f4792aef082a0e2d9d615229013663b14599abd011637daf8f185a20"
DIMS = ("Relevance", "Coherence", "Empathy", "Surprise", "Engagement", "Complexity")


def canonical(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode()


def sha256(value: bytes | Any) -> str:
    return hashlib.sha256(value if isinstance(value, bytes) else canonical(value)).hexdigest()


def _recovery_canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


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
        "analysis_rule": {"coverage": "include_every_finite_numeric_score_even_when_coverage_is_false", "primary": "absolute_error_per_item_then_equal_mean_across_4_prompt_groups"},
        "authority": {"confirmation": "none", "development_in_sample_only": True, "endpoint_pooling": "forbidden", "generalization": "none", "promotion": "none", "runtime": "none", "selection": "none", "sol": "unopened_separate_package"},
        "format_version": 1,
        "geometry": {"candidates": 2, "grok_cells": 8, "groups": 4, "items": 4, "max_concurrency": 10, "sol_cells": 0},
        "kind": "fresh_dspy_descendant_child20_train_pilot",
        "recovered_descendant": {"candidate_id": DESCENDANT, "candidate_sha256": DESCENDANT_SHA256, "instruction_sha256": DESCENDANT_INSTRUCTION_SHA256, "profile_sha256": DESCENDANT_PROFILE_SHA256, "source_sha256": RECOVERED_SHA256},
        "requested_judge": {"endpoint": "grok_primary", "model": "grok-4.6", "provider_attested": False, "reasoning": "high", "reported_model": "grok-4.6-build", "tools": "off"},
        "study_id": STUDY_ID,
    }
    if value != expected:
        raise ValueError("study contract drifted")
    return value


def _recovered_candidate(path: Path) -> dict[str, Any]:
    raw = Path(path).read_bytes()
    if hashlib.sha256(raw).hexdigest() != RECOVERED_SHA256:
        raise ValueError("recovered descendant source drifted")
    try:
        final = json.loads(raw.decode("utf-8"), parse_constant=lambda token: (_ for _ in ()).throw(ValueError(token)))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("recovered descendant is not canonical JSON") from error
    if not isinstance(final, dict) or _recovery_canonical(final) != raw or final.get("kind") != "recovered_dspy_native_development_descendant":
        raise ValueError("recovered descendant envelope drifted")
    descendant = final.get("descendant")
    if not isinstance(descendant, Mapping) or final.get("descendant_sha256") != hashlib.sha256(_recovery_canonical(dict(descendant))).hexdigest():
        raise ValueError("recovered descendant commitment drifted")
    commitment = descendant.get("candidate_commitment")
    if not isinstance(commitment, Mapping) or hashlib.sha256(_recovery_canonical(dict(commitment))).hexdigest() != DESCENDANT_SHA256:
        raise ValueError("recovered candidate commitment drifted")
    try:
        instruction = base64.b64decode(descendant["instruction_base64"], validate=True)
        profile = base64.b64decode(descendant["profile_base64"], validate=True)
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("recovered candidate byte encoding drifted") from error
    parent = descendant.get("parent")
    if (descendant.get("candidate_kind") != "dspy_native_train_instruction_descendant" or descendant.get("candidate_sha256") != DESCENDANT_SHA256
            or commitment.get("instruction_sha256") != DESCENDANT_INSTRUCTION_SHA256 or commitment.get("profile_sha256") != DESCENDANT_PROFILE_SHA256
            or sha256(instruction) != DESCENDANT_INSTRUCTION_SHA256 or sha256(profile) != DESCENDANT_PROFILE_SHA256 or not isinstance(parent, Mapping)):
        raise ValueError("recovered candidate binding drifted")
    return {"candidate_id": DESCENDANT, "candidate_sha256": DESCENDANT_SHA256, "instruction": instruction, "instruction_sha256": DESCENDANT_INSTRUCTION_SHA256, "profile_raw": profile, "profile_sha256": DESCENDANT_PROFILE_SHA256, "kind": "recovered_dspy_train_descendant", "recovered_descendant_sha256": final["descendant_sha256"], "parent": dict(parent)}


def schedule(*, split_manifest: Path, hanna_csv: Path, successor_contract: Path, recovered_descendant: Path = RECOVERED) -> dict[str, Any]:
    contract_value = contract(); v11 = load(V11, V11_COMMIT, V11_SHA256, "_v14_v11")
    v10 = v11.load(v11.V10, v11.V10_COMMIT, v11.V10_SHA256, "_v14_v10")
    validation = v10._module(v10.VALIDATION, v10.VALIDATION_SHA256, "_v14_validation")
    child = next((row for row in v10._panel(validation) if row["candidate_id"] == CHILD20), None)
    if not isinstance(child, Mapping):
        raise ValueError("pinned child20 candidate is absent")
    descendant = _recovered_candidate(Path(recovered_descendant))
    if child.get("profile_raw") != descendant["profile_raw"] or child.get("profile_sha256") != DESCENDANT_PROFILE_SHA256:
        raise ValueError("descendant profile is not byte-identical to child20")
    expected_parent = {"candidate_id": CHILD20, "candidate_sha256": child["candidate_sha256"], "instruction_sha256": child["instruction_sha256"], "profile_sha256": child["profile_sha256"]}
    if descendant["parent"] != expected_parent:
        raise ValueError("recovered descendant parent binding drifted")
    cells: list[dict[str, Any]] = []
    for item in v11.source_items(split_manifest=Path(split_manifest), hanna_csv=Path(hanna_csv), successor_contract=Path(successor_contract)):
        for candidate in (child, descendant):
            payload = v10._payload(validation, item, candidate)
            cells.append({"cell_id": "v14-train-" + sha256({"candidate": candidate["candidate_id"], "item": item["item_id"]})[:20], "ordinal": len(cells) + 1, "candidate_id": candidate["candidate_id"], "candidate_sha256": candidate["candidate_sha256"], "candidate_instruction_sha256": candidate["instruction_sha256"], "candidate_profile_sha256": candidate["profile_sha256"], "item_id": item["item_id"], "prompt_group_id": item["prompt_group_id"], "partition": "train", "source_binding_sha256": item["source_binding_sha256"], "target": item["target"], "target_sha256": sha256(item["target"]), "payload_base64": base64.b64encode(payload).decode("ascii"), "payload_sha256": sha256(payload), "endpoint_payload_sha256s": {"grok_primary": sha256(payload), "sol_later": sha256(payload)}})
    if len(cells) != 8 or len({row["cell_id"] for row in cells}) != 8 or len({row["item_id"] for row in cells}) != 4:
        raise ValueError("V14 pilot geometry drifted")
    value: dict[str, Any] = {"format_version": 1, "study_id": STUDY_ID, "kind": contract_value["kind"], "endpoint": "grok_primary", "requested_judge": contract_value["requested_judge"], "groups": [{"prompt_group_id": item["prompt_group_id"], "partition": "train"} for item in v11.source_items(split_manifest=Path(split_manifest), hanna_csv=Path(hanna_csv), successor_contract=Path(successor_contract))], "cells": cells, "geometry": contract_value["geometry"], "analysis_rule": contract_value["analysis_rule"], "authority": contract_value["authority"], "source": {"v11_study_sha256": V11_SHA256, "split_manifest_sha256": v11.SPLIT_SHA256, "hanna_csv_sha256": v11.CSV_SHA256, "successor_contract_sha256": v11.SUCCESSOR_SHA256, "recovered_descendant_sha256": RECOVERED_SHA256}}
    value["schedule_sha256"] = sha256(value)
    return value


def _v13_response() -> Callable[[ModuleType, bytes, Mapping[str, Any]], tuple[dict[str, Any], dict[str, Any]]]:
    raw = V13.read_bytes()
    if sha256(raw) != V13_SHA256:
        raise ValueError("pinned V13 response parser drifted")
    spec = importlib.util.spec_from_file_location("_v14_v13_response", V13)
    if spec is None or spec.loader is None:
        raise ValueError("V13 response parser cannot load")
    module = importlib.util.module_from_spec(spec); sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(spec.name, None)
    if V13.read_bytes() != raw or not callable(getattr(module, "_response", None)):
        raise ValueError("V13 response parser changed during load")
    return module._response


def _known_payloads(value: Mapping[str, Any]) -> set[bytes]:
    cells = value.get("cells")
    if not isinstance(cells, list) or len(cells) != 8:
        raise ValueError("V14 payload geometry drifted")
    payloads: set[bytes] = set()
    for row in cells:
        if not isinstance(row, Mapping) or not isinstance(row.get("payload_base64"), str) or not isinstance(row.get("payload_sha256"), str):
            raise ValueError("V14 payload binding drifted")
        try:
            raw = base64.b64decode(row["payload_base64"], validate=True)
        except ValueError as error:
            raise ValueError("V14 payload encoding drifted") from error
        writing = strict(raw, "frozen V14 outbound payload").get("writing")
        if sha256(raw) != row["payload_sha256"] or not isinstance(writing, Mapping) or set(writing) != {"prompt", "story"} or any(not isinstance(writing[name], str) for name in writing):
            raise ValueError("V14 payload wrapper drifted")
        payloads.add(raw)
    if len(payloads) != 8:
        raise ValueError("V14 payload uniqueness drifted")
    return payloads


@contextmanager
def bound(*, schedule_value: Mapping[str, Any]) -> Iterator[tuple[ModuleType, ModuleType, ModuleType, ModuleType]]:
    v11 = load(V11, V11_COMMIT, V11_SHA256, "_v14_bound_v11")
    with v11.bound(schedule_value=schedule_value) as (lifecycle, runtime, v9):
        original_study, original_precontact = lifecycle.STUDY_ID, v9._validate_precontact_payload
        known_payloads = _known_payloads(schedule_value)

        def exact_precontact(payload: bytes) -> None:
            if type(payload) is not bytes or payload not in known_payloads:
                raise ValueError("outbound payload is not an exact frozen V14 payload")

        lifecycle.STUDY_ID, v9._validate_precontact_payload = STUDY_ID, exact_precontact
        try:
            yield lifecycle, runtime, v9, v11
        finally:
            lifecycle.STUDY_ID, v9._validate_precontact_payload = original_study, original_precontact


def _disjoint_actual_sources(lifecycle: ModuleType, *, output_root: Path, queue_root: Path, split_manifest: Path, hanna_csv: Path, successor_contract: Path, recovered_descendant: Path) -> None:
    lifecycle._disjoint(Path(output_root), REPO, Path(queue_root), Path(split_manifest).parent, Path(hanna_csv).parent, Path(successor_contract).parent, Path(recovered_descendant).parent)


def prepare_all(*, output_root: Path, queue_root: Path, authorization_acknowledgement_sha256: str, split_manifest: Path, hanna_csv: Path, successor_contract: Path, route_provider: Callable[[Path], tuple[dict[str, Any], dict[str, Any]]], recovered_descendant: Path = RECOVERED) -> dict[str, Any]:
    value = schedule(split_manifest=split_manifest, hanna_csv=hanna_csv, successor_contract=successor_contract, recovered_descendant=recovered_descendant)
    with bound(schedule_value=value) as (lifecycle, runtime, v9, _v11):
        _disjoint_actual_sources(lifecycle, output_root=Path(output_root), queue_root=Path(queue_root), split_manifest=Path(split_manifest), hanna_csv=Path(hanna_csv), successor_contract=Path(successor_contract), recovered_descendant=Path(recovered_descendant))
        result = lifecycle.prepare_all(output_root=Path(output_root), queue_root=Path(queue_root), authorization_acknowledgement_sha256=authorization_acknowledgement_sha256, route_provider=v9._validated_route(v9.parent_stack(), runtime, Path(queue_root), route_provider), normalized_root=Path(output_root).parent / ".v14-normalized", materialization_root=Path(output_root).parent / ".v14-materialization", frozen_successor_path=Path(output_root).parent / ".v14-successor.json", hanna_csv_path=Path(output_root).parent / ".v14-source.csv")
    prepared = result.get("prepared_cells", []); expected = {row["cell_id"] for row in value["cells"]}
    if len(prepared) != 8 or set(prepared) != expected or (Path(output_root) / "schedule.json").read_bytes() != canonical(value):
        raise ValueError("lower lifecycle did not prepare exactly eight V14 cells")
    return {"study_id": STUDY_ID, "prepared_cells": prepared, "logical_cells": 8, "provider_calls_made": 0, "process_launches": 0}


def execute_wave(*, output_root: Path, queue_root: Path, authorization_acknowledgement_sha256: str, split_manifest: Path, hanna_csv: Path, successor_contract: Path, allow_remote: bool, route_provider: Callable[[Path], tuple[dict[str, Any], dict[str, Any]]], runner: Callable[..., Mapping[str, Any]] | None = None, recovered_descendant: Path = RECOVERED) -> list[dict[str, Any]]:
    if allow_remote is not True:
        raise ValueError("explicit allow_remote required")
    value = schedule(split_manifest=split_manifest, hanna_csv=hanna_csv, successor_contract=successor_contract, recovered_descendant=recovered_descendant)
    with bound(schedule_value=value) as (lifecycle, runtime, v9, v11):
        _disjoint_actual_sources(lifecycle, output_root=Path(output_root), queue_root=Path(queue_root), split_manifest=Path(split_manifest), hanna_csv=Path(hanna_csv), successor_contract=Path(successor_contract), recovered_descendant=Path(recovered_descendant))
        old = load(RECONCILE, RECONCILE_COMMIT, RECONCILE_SHA256, "_v14_response_helper")
        selected = v9.parent_stack()._guard_runner(runner or lifecycle.live()._default_runner, lifecycle, value)
        parser = _v13_response()

        async def launch() -> list[dict[str, Any]]:
            route, evidence = v9._validated_route(v9.parent_stack(), runtime, Path(queue_root), route_provider)(Path(queue_root)); gate = asyncio.Semaphore(10)

            async def one(cell_id: str) -> dict[str, Any]:
                async with gate:
                    return await asyncio.to_thread(v11._execute_bound, value=value, lifecycle=lifecycle, runtime=runtime, v9=v9, reconciler=SimpleNamespace(_response=parser), response_helper=old.helper(), selected=selected, output_root=Path(output_root), queue_root=Path(queue_root), authorization_acknowledgement_sha256=authorization_acknowledgement_sha256, cell_id=cell_id, route_provider=lambda _ignored: (route, evidence))

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


def report(*, output_root: Path, authorization_acknowledgement_sha256: str, split_manifest: Path, hanna_csv: Path, successor_contract: Path, recovered_descendant: Path = RECOVERED) -> dict[str, Any]:
    value = schedule(split_manifest=split_manifest, hanna_csv=hanna_csv, successor_contract=successor_contract, recovered_descendant=recovered_descendant)
    roots = Path(output_root); expected = {row["cell_id"] for row in value["cells"]}
    if not roots.is_dir() or {path.name for path in roots.iterdir()} != {"schedule.json", ".claims", *expected} or (roots / "schedule.json").read_bytes() != canonical(value):
        raise ValueError("incomplete or ambiguous V14 receipt inventory")
    old = load(RECONCILE, RECONCILE_COMMIT, RECONCILE_SHA256, "_v14_report_helper"); parser = _v13_response(); helper = old.helper()
    cells: list[dict[str, Any]] = []; grouped: dict[str, dict[str, list[dict[str, Any]]]] = {CHILD20: {}, DESCENDANT: {}}
    request_ids: set[str] = set(); session_ids: set[str] = set()
    expected_items = {group["prompt_group_id"]: {row["item_id"] for row in value["cells"] if row["prompt_group_id"] == group["prompt_group_id"]} for group in value["groups"]}
    with bound(schedule_value=value) as (lifecycle, _runtime, v9, _v11):
        source = lifecycle.live(); parent = v9.parent_stack(); v9._validate_claims(roots, expected)
        frozen_route: Mapping[str, Any] | None = None; frozen_evidence: Mapping[str, Any] | None = None
        for row in value["cells"]:
            root = roots / row["cell_id"]; stored = v9.strict(v9.stable(root / "prepared.json"), "prepared"); acknowledgement = v9.strict(v9.stable(root / "authorization-acknowledgement.json"), "acknowledgement")
            if acknowledgement.get("acknowledgement_sha256") != authorization_acknowledgement_sha256:
                raise ValueError("receipt acknowledgement drifted")
            route, evidence = stored.get("route"), stored.get("route_evidence")
            if not isinstance(route, Mapping) or not isinstance(evidence, Mapping):
                raise TypeError("ambiguous receipt route or evidence")
            if frozen_route is None: frozen_route, frozen_evidence = route, evidence
            elif route != frozen_route or evidence != frozen_evidence: raise ValueError("mixed receipt route or evidence")
            raw, prompt, schema = lifecycle.payload(row)
            request, response, identity, _settings = lifecycle.admit(root, row, value, raw, prompt, schema, route, evidence, authorization_acknowledgement_sha256, source)
            envelope, _identity = parser(helper, response, route); structured = envelope["structuredOutput"]; scores, coverage = structured["scores"], structured["coverage"]
            request_id, session_id = identity.get("request_id") if isinstance(identity, Mapping) else None, identity.get("session_id") if isinstance(identity, Mapping) else None
            if not isinstance(request_id, str) or not request_id or request_id in request_ids or not isinstance(session_id, str) or not session_id or session_id in session_ids:
                raise ValueError("duplicate or invalid native identity")
            request_ids.add(request_id); session_ids.add(session_id)
            cell = {"cell_id": row["cell_id"], "candidate_id": row["candidate_id"], "item_id": row["item_id"], "prompt_group_id": row["prompt_group_id"], "partition": "train", "payload_sha256": row["payload_sha256"], "native_request_sha256": sha256(request), "native_response_sha256": sha256(response), "scores": {dimension: float(scores[dimension]) for dimension in DIMS}, "coverage": {dimension: coverage[dimension] for dimension in DIMS}, "target": {dimension: float(row["target"][dimension]) for dimension in DIMS}}
            cell["per_item_mae"] = _mean([abs(cell["scores"][dimension] - cell["target"][dimension]) for dimension in DIMS]); grouped[row["candidate_id"]].setdefault(row["prompt_group_id"], []).append(cell); cells.append(cell)
        if frozen_route is None or frozen_evidence is None: raise ValueError("missing V14 route evidence")
        lifecycle.validate_frozen_route(frozen_route, frozen_evidence); parent._validate_route_evidence(frozen_route, frozen_evidence)
    if len(cells) != 8 or len(request_ids) != 8 or len(session_ids) != 8: raise ValueError("incomplete V14 receipt projection")
    metrics: list[dict[str, Any]] = []
    for candidate in (CHILD20, DESCENDANT):
        by_group = grouped[candidate]
        if set(by_group) != set(expected_items) or any({row["item_id"] for row in by_group[group]} != expected_items[group] or len(by_group[group]) != len(expected_items[group]) for group in expected_items): raise ValueError("candidate TRAIN grouping drifted")
        group_mae = {group: _mean([row["per_item_mae"] for row in by_group[group]]) for group in sorted(by_group)}
        metrics.append({"candidate_id": candidate, "per_group_mean_item_mae": group_mae, "equal_group_mean_item_mae": _mean(list(group_mae.values())), "item_count": 4, "group_count": 4})
    child, descendant = metrics; primary_child, primary_descendant = child["equal_group_mean_item_mae"], descendant["equal_group_mean_item_mae"]
    return {"format_version": 1, "study_id": STUDY_ID, "kind": "receipt_derived_8_cell_grok_train_pilot_report", "endpoint": "grok_primary", "authority": contract()["authority"], "analysis_rule": contract()["analysis_rule"], "native_endpoint_contact_cardinality": "unproven", "cells": cells, "unique_request_ids": len(request_ids), "unique_session_ids": len(session_ids), "metrics": metrics, "comparison": {"child20_candidate_id": CHILD20, "descendant_candidate_id": DESCENDANT, "descendant_minus_child20": primary_descendant - primary_child, "relative_reduction": (primary_child - primary_descendant) / primary_child if primary_child else None, "strict_primary_mae_improvement": primary_descendant < primary_child}, "interpretation": "development_in_sample_screen_only; no_selection_or_promotion_or_generalization; no_automatic_sol_dispatch"}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument("--inspect", action="store_true"); parser.add_argument("--split-manifest", type=Path, required=True); parser.add_argument("--hanna-csv", type=Path, required=True); parser.add_argument("--successor-contract", type=Path, required=True); parser.add_argument("--recovered-descendant", type=Path, default=RECOVERED)
    args = parser.parse_args(argv)
    if not args.inspect: parser.error("only provider-free --inspect is available from the CLI")
    value = schedule(split_manifest=args.split_manifest, hanna_csv=args.hanna_csv, successor_contract=args.successor_contract, recovered_descendant=args.recovered_descendant)
    print(canonical({"study_id": STUDY_ID, "cells": len(value["cells"]), "items": 4, "groups": 4, "provider_calls_made": 0, "process_launches": 0}).decode(), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
