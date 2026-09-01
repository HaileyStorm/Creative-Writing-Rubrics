#!/usr/bin/env python3
"""Execute only the frozen Fresh96 future-confirmation Grok cells."""
from __future__ import annotations

import argparse
import base64
import importlib.util
import json
import math
import sys
from collections import defaultdict
from collections.abc import Callable, Mapping
from pathlib import Path
from types import ModuleType
from typing import Any

HERE = Path(__file__).resolve().parent
STUDY_ID = "hbq-human-alignment-optimizer-v10-fresh96-confirmation-grok-exec-v1"
FREEZE = HERE.parent / "hbq-human-alignment-optimizer-v10-fresh96-confirmation-candidates-v1"
BASE = HERE.parent / "hbq-human-alignment-optimizer-v9-desc18-broad-replication-grok-exec-v1" / "executor.py"
BASE_SHA256 = "d719d484fabc12110fe36f61c379edf8d15aa701f97f025d1ff2ac24f1d2f4a4"
FREEZE_STUDY_SHA256 = "38ea9c9c0cf96dfc0ca32b64ee6639515600bc01b93e204cdd397bae393b2a6f"
FREEZE_CONTRACT_SHA256 = "acf8fbf0f3ef5937d963e53fecf286ae3a606eb62302b0e918468e74b17d9348"
MAX_CONCURRENCY = 10
BASELINE = "candidate-102cc7f06c9a99a7"
CHILD = "broader-nextwave-20-missing_evidence_not_no-referent-evidence"
DIMENSIONS = ("Relevance", "Coherence", "Empathy", "Surprise", "Engagement", "Complexity")


def _load_base() -> ModuleType:
    raw = BASE.read_bytes()
    if __import__("hashlib").sha256(raw).hexdigest() != BASE_SHA256:
        raise ValueError("pinned V9 Grok executor drifted")
    spec = importlib.util.spec_from_file_location("_v10_pinned_v9_grok", BASE)
    if spec is None or spec.loader is None:
        raise ValueError("pinned V9 Grok executor cannot load")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(spec.name, None)
    return module


def _contract() -> dict[str, Any]:
    base = _load_base()
    value = base.strict(base.stable(HERE / "study-contract.json"), "study contract")
    expected = {
        "authority": {"confirmation": "measurement_only", "endpoint_pooling": "forbidden", "promotion": "none", "runtime": "none", "selection": "none", "sol": "not_implemented"},
        "format_version": 1,
        "geometry": {"candidates": 2, "future_confirmation_groups": 16, "future_confirmation_items": 32, "grok_cells": 64, "sol_cells": 0},
        "kind": "fresh96_future_confirmation_grok_execution",
        "prohibitions": ["tools disabled", "no fallback or resend", "no targets outbound", "no Sol execution", "no selection promotion runtime or general claim"],
        "study_id": STUDY_ID,
    }
    if value != expected:
        raise ValueError("execution contract drifted")
    return value


def freeze_module() -> ModuleType:
    path = FREEZE / "study.py"
    contract = FREEZE / "study-contract.json"
    if (__import__("hashlib").sha256(path.read_bytes()).hexdigest() != FREEZE_STUDY_SHA256
            or __import__("hashlib").sha256(contract.read_bytes()).hexdigest() != FREEZE_CONTRACT_SHA256):
        raise ValueError("pinned future-confirmation freeze drifted")
    spec = importlib.util.spec_from_file_location("_v10_future_freeze", path)
    if spec is None or spec.loader is None:
        raise ValueError("future-confirmation freeze cannot load")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def frozen_schedule(freeze_root: Path) -> dict[str, Any]:
    module = freeze_module()
    schedule = module.validate_frozen_root(Path(freeze_root))
    expected_geometry = {"candidates": 2, "future_confirmation_groups": 16, "future_confirmation_items": 32, "grok_cells": 64, "sol_cells": 0}
    cells = schedule.get("cells")
    if (schedule.get("study_id") != module.STUDY_ID or schedule.get("geometry") != expected_geometry
            or not isinstance(cells, list) or len(cells) != 64
            or len({row.get("item_id") for row in cells if isinstance(row, Mapping)}) != 32
            or len({row.get("prompt_group_id") for row in cells if isinstance(row, Mapping)}) != 16
            or {row.get("candidate_id") for row in cells if isinstance(row, Mapping)} != {BASELINE, CHILD}):
        raise ValueError("future-confirmation freeze identity drifted")
    for row in cells:
        if not isinstance(row, Mapping) or row.get("endpoint_payload_sha256s") != {"grok_primary": row.get("payload_sha256"), "sol_later": row.get("payload_sha256")}:
            raise ValueError("cross-endpoint payload parity drifted")
        payload = base64.b64decode(str(row.get("payload_base64", "")), validate=True)
        decoded = module.strict(payload, "outbound payload")
        if "target" in decoded or "target" in decoded.get("writing", {}) or "tools" in decoded:
            raise ValueError("target leakage or tool surface in outbound payload")
    value = dict(schedule)
    value.update({"study_id": STUDY_ID, "kind": "frozen_fresh96_future_confirmation_grok_execution_schedule", "authority": {"provider_calls_made": 0, "process_launches": 0, "selection": "none", "promotion": "none", "runtime": "none", "sol": "not_implemented", "confirmation": {"status": "measurement_only", "cells": 64}}, "frozen_schedule_sha256": schedule["schedule_sha256"]})
    value["geometry"] = {"candidates": 2, "confirmation_cells": 64, "future_confirmation_groups": 16, "future_confirmation_items": 32, "grok_cells": 64, "sol_cells": 0}
    value.pop("schedule_sha256", None)
    value["schedule_sha256"] = module.sha256(value)
    _contract()
    return value


def _configured_base() -> ModuleType:
    base = _load_base()
    base.STUDY_ID = STUDY_ID
    base.MAX_CONCURRENCY = MAX_CONCURRENCY
    base.frozen_schedule = frozen_schedule
    base._validate_contract = _contract
    return base


def _tools_disabled(settings: Mapping[str, Any]) -> None:
    if settings.get("tools_enabled") is not False:
        raise ValueError("native effective settings did not disable tools")


def prepare_all(*, output_root: Path, freeze_root: Path, queue_root: Path, authorization_acknowledgement_sha256: str, route_provider: Callable[[Path], tuple[dict[str, Any], dict[str, Any]]] | None = None) -> dict[str, Any]:
    result = _configured_base().prepare_all(output_root=Path(output_root), freeze_root=Path(freeze_root), queue_root=Path(queue_root), authorization_acknowledgement_sha256=authorization_acknowledgement_sha256, route_provider=route_provider)
    if result.get("provider_calls_made") != 0 or result.get("process_launches") != 0 or len(result.get("prepared_cells", [])) != 64:
        raise ValueError("preparation lifecycle drifted")
    result["kind"] = "prepared_64_fresh96_future_confirmation_grok_cells"
    return result


def execute_one(*, output_root: Path, freeze_root: Path, queue_root: Path, authorization_acknowledgement_sha256: str, cell_id: str, allow_remote: bool, route_provider: Callable[[Path], tuple[dict[str, Any], dict[str, Any]]] | None = None, runner: Callable[..., Mapping[str, Any]] | None = None) -> dict[str, Any]:
    if allow_remote is not True:
        raise ValueError("explicit allow_remote required")
    return _configured_base().execute_one(output_root=Path(output_root), freeze_root=Path(freeze_root), queue_root=Path(queue_root), authorization_acknowledgement_sha256=authorization_acknowledgement_sha256, cell_id=cell_id, allow_remote=True, route_provider=route_provider, runner=runner)


async def execute_wave(*, output_root: Path, freeze_root: Path, queue_root: Path, authorization_acknowledgement_sha256: str, allow_remote: bool, route_provider: Callable[[Path], tuple[dict[str, Any], dict[str, Any]]] | None = None, runner: Callable[..., Mapping[str, Any]] | None = None) -> list[dict[str, Any]]:
    if allow_remote is not True:
        raise ValueError("explicit allow_remote required")
    values = await _configured_base().execute_wave(output_root=Path(output_root), freeze_root=Path(freeze_root), queue_root=Path(queue_root), authorization_acknowledgement_sha256=authorization_acknowledgement_sha256, allow_remote=True, route_provider=route_provider, runner=runner)
    if len(values) != 64:
        raise ValueError("execution wave cardinality drifted")
    return values


def finalize_collector(*, output_root: Path, freeze_root: Path, collector_output: Path, authorization_acknowledgement_sha256: str) -> dict[str, Any]:
    base = _configured_base()
    with base._bound_source(freeze_root=Path(freeze_root)) as (lifecycle, source, schedule, parent, _runtime):
        collector = base._safe(Path(collector_output))
        if collector.exists():
            raise ValueError("collector output must be fresh")
        expected_cells = {row["cell_id"] for row in schedule["cells"]}
        if ({path.name for path in Path(output_root).iterdir()} != {"schedule.json", ".claims", *expected_cells}
                or base.stable(Path(output_root) / "schedule.json") != base.canonical(schedule)):
            raise ValueError("output schedule inventory drifted")
        base._validate_claims(Path(output_root), expected_cells)
        cells: list[dict[str, Any]] = []
        frozen_route: Mapping[str, Any] | None = None
        frozen_evidence: Mapping[str, Any] | None = None
        for row in schedule["cells"]:
            request, response, identity, settings, stored = base._admit_cell(lifecycle, source, Path(output_root), row, schedule, authorization_acknowledgement_sha256)
            if not isinstance(settings, Mapping):
                raise TypeError("native effective settings are invalid")
            _tools_disabled(settings)
            if frozen_route is None:
                frozen_route, frozen_evidence = stored["route"], stored["route_evidence"]
            if stored["route"] != frozen_route or stored["route_evidence"] != frozen_evidence:
                raise ValueError("collector route/evidence differs across cells")
            cells.append({"cell_id": row["cell_id"], "payload_base64": row["payload_base64"], "payload_sha256": row["payload_sha256"], "native_request_base64": base64.b64encode(request).decode("ascii"), "native_request_sha256": base.sha256(request), "native_response_base64": base64.b64encode(response).decode("ascii"), "native_response_sha256": base.sha256(response), "identity": identity, "effective_settings": settings, "effective_settings_sha256": base.sha256(settings)})
        if frozen_route is None or frozen_evidence is None:
            raise ValueError("collector has no cells")
        parent._validate_route_evidence(frozen_route, frozen_evidence)
        value = {"format_version": 1, "study_id": STUDY_ID, "kind": "complete_64_fresh96_future_confirmation_grok_receipts_cardinality_unproven", "schedule_sha256": schedule["schedule_sha256"], "authorization_acknowledgement_sha256": authorization_acknowledgement_sha256, "route": frozen_route, "route_evidence": frozen_evidence, "cells": cells, "native_endpoint_contact_cardinality": "unproven", "provider_calls_made": None, "process_launches": 64}
        lifecycle.write_new(collector, base.canonical(value))
        return {"format_version": 1, "study_id": STUDY_ID, "kind": value["kind"], "collector_sha256": base.sha256(value), "cells": 64, "native_endpoint_contact_cardinality": "unproven", "provider_calls_made": None, "process_launches": 64}


def replay_collector(*, output_root: Path, freeze_root: Path, collector_path: Path) -> dict[str, Any]:
    base = _configured_base()
    with base._bound_source(freeze_root=Path(freeze_root)) as (lifecycle, source, schedule, parent, _runtime):
        collector = base.strict(base.stable(Path(collector_path)), "collector")
        expected_fields = {"format_version", "study_id", "kind", "schedule_sha256", "authorization_acknowledgement_sha256", "route", "route_evidence", "cells", "native_endpoint_contact_cardinality", "provider_calls_made", "process_launches"}
        if (set(collector) != expected_fields or collector.get("format_version") != 1 or collector.get("study_id") != STUDY_ID
                or collector.get("kind") != "complete_64_fresh96_future_confirmation_grok_receipts_cardinality_unproven"
                or collector.get("schedule_sha256") != schedule["schedule_sha256"] or collector.get("native_endpoint_contact_cardinality") != "unproven"
                or collector.get("provider_calls_made") is not None or collector.get("process_launches") != 64
                or not isinstance(collector.get("route"), Mapping) or not isinstance(collector.get("route_evidence"), Mapping)
                or not isinstance(collector.get("cells"), list) or len(collector["cells"]) != 64):
            raise ValueError("collector drifted")
        parent._validate_route_evidence(collector["route"], collector["route_evidence"])
        index = {row["cell_id"]: row for row in schedule["cells"]}
        base._validate_claims(Path(output_root), set(index))
        seen: set[tuple[str, str]] = set()
        for supplied in collector["cells"]:
            expected_cell = {"cell_id", "payload_base64", "payload_sha256", "native_request_base64", "native_request_sha256", "native_response_base64", "native_response_sha256", "identity", "effective_settings", "effective_settings_sha256"}
            if not isinstance(supplied, Mapping) or set(supplied) != expected_cell or supplied.get("cell_id") not in index:
                raise ValueError("collector cell drifted")
            row = index[supplied["cell_id"]]
            request, response, identity, settings, stored = base._admit_cell(lifecycle, source, Path(output_root), row, schedule, str(collector["authorization_acknowledgement_sha256"]))
            if not isinstance(settings, Mapping):
                raise TypeError("native effective settings are invalid")
            _tools_disabled(settings)
            supplied_request = base64.b64decode(supplied["native_request_base64"], validate=True)
            supplied_response = base64.b64decode(supplied["native_response_base64"], validate=True)
            if (stored["route"] != collector["route"] or stored["route_evidence"] != collector["route_evidence"]
                    or supplied["payload_base64"] != row["payload_base64"] or supplied["payload_sha256"] != row["payload_sha256"]
                    or supplied_request != request or supplied_response != response
                    or supplied["native_request_sha256"] != base.sha256(request) or supplied["native_response_sha256"] != base.sha256(response)
                    or supplied["identity"] != identity or supplied["effective_settings"] != settings or supplied["effective_settings_sha256"] != base.sha256(settings)):
                raise ValueError("collector native receipt differs from persisted execution")
            key = (identity.get("request_id"), identity.get("session_id")) if isinstance(identity, Mapping) else ("", "")
            if not all(key) or key in seen:
                raise ValueError("duplicate or invalid native identity")
            seen.add(key)
        if set(index) != {row.get("cell_id") for row in collector["cells"]}:
            raise ValueError("partial collector")
        return {"format_version": 1, "study_id": STUDY_ID, "collector_sha256": base.sha256(collector), "cells": 64, "provider_calls_made": None, "process_launches": 64, "equal_group_projection_ready": True, "native_endpoint_contact_cardinality": "unproven", "authority": {"selection": "none", "promotion": "none", "runtime": "none", "confirmation": {"status": "measurement_only", "cells": 64}, "endpoint_pooling": "forbidden", "sol": "not_implemented"}}


def project_collector(*, output_root: Path, freeze_root: Path, collector_path: Path) -> dict[str, Any]:
    base = _configured_base()
    replay = replay_collector(output_root=Path(output_root), freeze_root=Path(freeze_root), collector_path=Path(collector_path))
    schedule = frozen_schedule(Path(freeze_root))
    collector = base.strict(base.stable(Path(collector_path)), "collector")
    by_cell = {row["cell_id"]: row for row in schedule["cells"]}
    received = collector.get("cells")
    if not isinstance(received, list) or len(received) != 64 or set(by_cell) != {row.get("cell_id") for row in received if isinstance(row, Mapping)}:
        raise ValueError("projection requires exactly all 64 completed cells")
    group_errors: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    for receipt in received:
        if not isinstance(receipt, Mapping):
            raise TypeError("collector cell shape drifted")
        row = by_cell[str(receipt["cell_id"])]
        response = base.strict(base64.b64decode(str(receipt.get("native_response_base64", "")), validate=True), "native response")
        structured = response.get("structuredOutput")
        scores = structured.get("scores") if isinstance(structured, Mapping) else None
        if not isinstance(scores, Mapping) or set(scores) != set(DIMENSIONS):
            raise ValueError("native score shape drifted")
        errors = []
        for dimension in DIMENSIONS:
            score, target = scores[dimension], row["target"][dimension]
            if type(score) not in (int, float) or not math.isfinite(float(score)) or type(target) not in (int, float):
                raise ValueError("non-finite score or target")
            errors.append(abs(float(score) - float(target)))
        group_errors[row["candidate_id"]][row["prompt_group_id"]].append(sum(errors) / len(errors))
    metrics = []
    for candidate in (BASELINE, CHILD):
        groups = group_errors.get(candidate, {})
        if len(groups) != 16 or any(len(errors) != 2 for errors in groups.values()):
            raise ValueError("projection requires complete candidate/group pairing")
        group_mae = {group: sum(errors) / len(errors) for group, errors in sorted(groups.items())}
        metrics.append({"candidate_id": candidate, "cells": 32, "equal_group_mae": sum(group_mae.values()) / len(group_mae), "group_mae": group_mae})
    baseline, child = metrics
    return {"format_version": 1, "study_id": STUDY_ID, "kind": "independent_fresh96_future_confirmation_grok_projection", "endpoint": "grok_primary", "endpoint_pooling": "forbidden", "cells": 64, "groups": 16, "metrics": metrics, "comparison": {"baseline_candidate_id": BASELINE, "child_candidate_id": CHILD, "child_minus_baseline": child["equal_group_mae"] - baseline["equal_group_mae"], "direction": "negative_favors_child20"}, "receipt_replay": replay, "authority": {"selection": "none", "promotion": "none", "runtime": "none", "sol": "not_implemented"}}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    for name in ("prepare-all", "execute-one", "execute-wave", "finalize-collector", "replay-collector", "project-collector"):
        modes.add_argument("--" + name, action="store_true")
    parser.add_argument("--output-root", type=Path, required=True); parser.add_argument("--freeze-root", type=Path, required=True); parser.add_argument("--queue-root", type=Path); parser.add_argument("--collector-output", type=Path); parser.add_argument("--collector-path", type=Path); parser.add_argument("--authorization-acknowledgement-sha256"); parser.add_argument("--cell-id"); parser.add_argument("--allow-remote", action="store_true")
    args = parser.parse_args(argv)
    common = {"output_root": args.output_root, "freeze_root": args.freeze_root}
    if args.prepare_all:
        if args.allow_remote or not args.queue_root or not args.authorization_acknowledgement_sha256: parser.error("prepare requires queue/acknowledgement and forbids remote execution")
        result = prepare_all(**common, queue_root=args.queue_root, authorization_acknowledgement_sha256=args.authorization_acknowledgement_sha256)
    elif args.execute_one:
        if not args.allow_remote or not args.queue_root or not args.authorization_acknowledgement_sha256 or not args.cell_id: parser.error("execute-one requires queue/acknowledgement/cell and explicit remote execution")
        result = execute_one(**common, queue_root=args.queue_root, authorization_acknowledgement_sha256=args.authorization_acknowledgement_sha256, cell_id=args.cell_id, allow_remote=True)
    elif args.execute_wave:
        if not args.allow_remote or not args.queue_root or not args.authorization_acknowledgement_sha256: parser.error("execute-wave requires queue/acknowledgement and explicit remote execution")
        import asyncio
        result = asyncio.run(execute_wave(**common, queue_root=args.queue_root, authorization_acknowledgement_sha256=args.authorization_acknowledgement_sha256, allow_remote=True))
    elif args.finalize_collector:
        if not args.collector_output or not args.authorization_acknowledgement_sha256: parser.error("finalize requires collector output and acknowledgement")
        result = finalize_collector(**common, collector_output=args.collector_output, authorization_acknowledgement_sha256=args.authorization_acknowledgement_sha256)
    elif args.replay_collector:
        if not args.collector_path: parser.error("replay requires collector path")
        result = replay_collector(**common, collector_path=args.collector_path)
    else:
        if not args.collector_path: parser.error("projection requires collector path")
        result = project_collector(**common, collector_path=args.collector_path)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
