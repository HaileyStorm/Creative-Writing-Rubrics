"""Native V17 endpoint execution, composed from the pinned V16 lifecycle.

This module deliberately has no command-line dispatch.  A reviewed caller must
provide a current zero-charge route proof, acknowledgement, and explicit
``allow_remote=True`` before any provider-capable function is reachable.
"""
from __future__ import annotations

import base64
import hashlib
import importlib.util
import json
import stat
import subprocess
import sys
from collections.abc import Callable, Mapping
from pathlib import Path
from types import ModuleType
from typing import Any

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
STUDY_ID = "hbq-human-alignment-optimizer-v17-comparative-train-replication-native-v1"
SOURCE_STUDY_ID = "hbq-human-alignment-optimizer-v17-comparative-train-replication-v1"
CONTRACT = HERE / "study-contract.json"
CONTRACT_SHA256 = "79125790dc4112e48e1f3a33e27719191c3ad576ba0069c37fa162a042892757"
CORE = HERE.parent / "hbq-human-alignment-optimizer-v17-comparative-train-replication-v1" / "study.py"
CORE_COMMIT = "3715be8"
CORE_CONTRACT_SHA256 = "959db50f36a2d9660f8dd9a8f38fade293d5196b18ddb6669365a6a86f2710eb"
V16_EXECUTOR = REPO / "evaluation-results/hbq-human-alignment-optimizer-v16-comparative-train-v1/executor.py"
V16_EXECUTOR_COMMIT = "3c1bec6"
V16_EXECUTOR_SHA256 = "554c6ab1e70a74a89c9b7cefab7c15ea66146a44aea7a8d38293ae6c2d4956db"
ENDPOINTS = {"grok", "sol"}
DIRECT, FORWARD, REVERSE = "direct_integer", "comparative_forward", "comparative_reverse"
DIMS = ("Relevance", "Coherence", "Empathy", "Surprise", "Engagement", "Complexity")
MAX_CONCURRENCY = 10


def canonical(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")


def sha256(value: bytes | Any) -> str:
    return hashlib.sha256(value if isinstance(value, bytes) else canonical(value)).hexdigest()


def _stable(path: Path) -> bytes:
    before = path.lstat()
    if not stat.S_ISREG(before.st_mode) or getattr(before, "st_file_attributes", 0) & 0x400:
        raise ValueError("runtime input must be a plain file")
    raw = path.read_bytes()
    after = path.lstat()
    if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns):
        raise ValueError("runtime input changed during read")
    return raw


def _pinned_bytes(path: Path, digest: str, commit: str) -> bytes:
    raw = _stable(path)
    relative = Path(path).relative_to(REPO).as_posix()
    blob = subprocess.run(["git", "-C", str(REPO), "show", f"{commit}:{relative}"], capture_output=True, check=False)
    if blob.returncode or sha256(raw) != digest or blob.stdout != raw:
        raise ValueError("pinned runtime dependency drifted")
    return raw


def _load_exact(path: Path, digest: str, commit: str, name: str) -> ModuleType:
    raw = _pinned_bytes(path, digest, commit)
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ValueError("pinned runtime dependency cannot load")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        exec(compile(raw, str(path), "exec"), module.__dict__)  # noqa: S102 - execute only the verified Git blob bytes
        if _stable(path) != raw:
            raise ValueError("pinned runtime changed during load")
    finally:
        sys.modules.pop(name, None)
    return module


def _core(expected_core_sha256: str) -> ModuleType:
    if len(expected_core_sha256) != 64 or sha256(CORE.read_bytes()) != expected_core_sha256:
        raise ValueError("explicit V17 core hash does not bind current source")
    return _load_exact(CORE, expected_core_sha256, CORE_COMMIT, "_v17_core")


def _resolution(*, split_manifest: Path, hanna_csv: Path, successor_contract: Path, expected_core_sha256: str) -> dict[str, Any]:
    if sha256(_stable(CONTRACT)) != CONTRACT_SHA256:
        raise ValueError("V17 native contract drifted")
    _pinned_bytes(CORE.with_name("experiment-contract.json"), CORE_CONTRACT_SHA256, CORE_COMMIT)
    core = _core(expected_core_sha256)
    paths = {
        "split_manifest": Path(split_manifest).resolve(),
        "hanna_csv": Path(hanna_csv).resolve(),
        "successor_contract": Path(successor_contract).resolve(),
    }
    schedule = core.schedule(**paths)
    committed = dict(schedule)
    schedule_sha256 = committed.pop("schedule_sha256", None)
    cells, reused = schedule.get("cells"), schedule.get("reused_direct_cells")
    if (
        not isinstance(cells, list)
        or not isinstance(reused, list)
        or schedule.get("study_id") != SOURCE_STUDY_ID
        or schedule.get("geometry", {}).get("logical_cells") != 48
        or schedule_sha256 != sha256(committed)
        or schedule.get("authority", {}).get("endpoint_pooling") != "forbidden"
        or len(cells) != 48
        or len(reused) != 12
    ):
        raise ValueError("V17 frozen schedule binding drifted")
    payloads: dict[str, bytes] = {}
    for row in cells:
        if not isinstance(row, Mapping) or row.get("condition") not in {DIRECT, FORWARD, REVERSE} or not isinstance(row.get("cell_id"), str):
            raise ValueError("V17 executable row drifted")
        raw = base64.b64decode(str(row.get("payload_base64", "")), validate=True)
        if row.get("payload_sha256") != sha256(raw) or row.get("endpoint_payload_sha256s") != {"grok_primary": sha256(raw), "sol_later": sha256(raw)}:
            raise ValueError("V17 endpoint payload parity drifted")
        payloads[row["cell_id"]] = raw
    if len(payloads) != 48 or sum(row["condition"] == DIRECT for row in cells) != 38 or sum(row["condition"] in {FORWARD, REVERSE} for row in cells) != 10:
        raise ValueError("V17 fresh-call geometry drifted")
    return {"core": core, "schedule": schedule, "schedule_sha256": schedule_sha256, "new": tuple(cells), "reused": tuple(reused), "payloads": payloads, "source_paths": paths, "core_sha256": expected_core_sha256}


def _execution_schedule(resolution: Mapping[str, Any]) -> dict[str, Any]:
    value: dict[str, Any] = {
        "format_version": 1,
        "study_id": STUDY_ID,
        "cells": list(resolution["new"]),
        "v17_core_sha256": resolution["core_sha256"],
        "v17_schedule_sha256": resolution["schedule_sha256"],
        "v17_native_contract_sha256": CONTRACT_SHA256,
        "runtime": {"v16_executor_commit": V16_EXECUTOR_COMMIT, "v16_executor_sha256": V16_EXECUTOR_SHA256},
    }
    value["schedule_sha256"] = sha256(value)
    return value


def _source_roots(resolution: Mapping[str, Any]) -> tuple[Path, ...]:
    return tuple(path.parent for path in resolution["source_paths"].values())


def _sol_rows(runtime: ModuleType, resolution: Mapping[str, Any]) -> tuple[dict[str, Any], ...]:
    panel = resolution["schedule"].get("panel")
    if not isinstance(panel, list):
        raise TypeError("V17 panel is unavailable")
    targets = {str(item["item_id"]): item["target"] for item in panel if isinstance(item, Mapping) and isinstance(item.get("item_id"), str) and isinstance(item.get("target"), Mapping)}
    if len(targets) != 50:
        raise ValueError("V17 panel target geometry drifted")
    rows: list[dict[str, Any]] = []
    for source in resolution["new"]:
        row = dict(source)
        row.update({"source_cell_id": str(source["cell_id"]), "candidate_id": str(source["condition"]), "payload_parity": "v17_core_endpoint_payload_exact"})
        if source["condition"] == DIRECT:
            item_id = source.get("item_id")
            if not isinstance(item_id, str) or item_id not in targets:
                raise ValueError("V17 direct target binding drifted")
            row.update({"story_id": item_id, "target": targets[item_id]})
        else:
            item_ids = source.get("item_ids")
            if not isinstance(item_ids, list) or len(item_ids) != 10 or len(set(item_ids)) != 10 or any(item_id not in targets for item_id in item_ids):
                raise ValueError("V17 batch target binding drifted")
            row.update({"item_id": "batch:" + str(source["cell_id"]), "story_id": "batch:" + str(source["cell_id"]), "target": {item_id: targets[item_id] for item_id in item_ids}})
        rows.append(row)
    if len(rows) != 48 or len({row["cell_id"] for row in rows}) != 48:
        raise ValueError("V17 Sol row geometry drifted")
    return tuple(sorted(rows, key=lambda row: str(row["cell_id"])))


def _grok_fresh(runtime: ModuleType, resolution: Mapping[str, Any], *, output_root: Path, acknowledgement: str) -> dict[str, dict[str, Any]]:
    measurements: dict[str, dict[str, Any]] = {}
    with runtime._grok_bound(resolution) as (lifecycle, _remote, v9, _v11, v13, v15):
        helper = v13.load(v13.RECONCILE, v13.RECONCILE_COMMIT, v13.RECONCILE_SHA256, "_v17_grok_report_helper").helper()
        expected = {str(row["cell_id"]) for row in resolution["new"]}
        v9._validate_claims(Path(output_root), expected)
        route = evidence = None
        identities: set[tuple[str, str]] = set()
        for row in resolution["new"]:
            admitted = runtime._grok_admit(resolution, lifecycle=lifecycle, v9=v9, v15=v15, helper=helper, output_root=Path(output_root), acknowledgement=acknowledgement, row=row)
            identity = admitted["identity"]
            key = (str(identity.get("request_id")), str(identity.get("session_id")))
            if not all(key) or key in identities:
                raise ValueError("duplicate or missing V17 Grok identity")
            identities.add(key)
            if route is None:
                route, evidence = admitted["route"], admitted["route_evidence"]
            elif route != admitted["route"] or evidence != admitted["route_evidence"]:
                raise ValueError("mixed V17 Grok route or evidence")
            root = Path(output_root) / str(row["cell_id"])
            measurements[str(row["cell_id"])] = {
                "condition": row["condition"],
                "answer": admitted["answer"],
                "provenance": {
                    "receipt_sha256": sha256(v9.stable(root / "execution-receipt.json")),
                    "raw_response_sha256": sha256(admitted["response"]),
                    "endpoint": "grok_primary",
                    "request_id": key[0],
                    "session_id": key[1],
                },
            }
        if len(measurements) != 48 or len(identities) != 48 or route is None or evidence is None:
            raise ValueError("V17 Grok fresh receipt geometry is incomplete")
        lifecycle.validate_frozen_route(route, evidence)
        v9.parent_stack()._validate_route_evidence(route, evidence)
    return measurements


def _sol_fresh(runtime: ModuleType, resolution: Mapping[str, Any], *, output_root: Path, acknowledgement: str) -> dict[str, dict[str, Any]]:
    lifecycle, base, rows = runtime._sol_runtime(resolution)
    entries = lifecycle._output_inventory(Path(output_root), rows)
    v4 = lifecycle.sol_v4()
    route = evidence = None
    identities: set[tuple[str, str]] = set()
    measurements: dict[str, dict[str, Any]] = {}
    for row in rows:
        admitted = runtime._sol_admit(resolution, lifecycle=lifecycle, runtime=base, row=row, output_root=Path(output_root), acknowledgement=acknowledgement)
        identity = admitted["identity"]
        key = (str(identity.get("thread_id")), str(identity.get("session_id")))
        if not all(key) or key in identities:
            raise ValueError("duplicate or missing V17 Sol identity")
        identities.add(key)
        if route is None:
            route, evidence = admitted["route"], admitted["route_evidence"]
        elif route != admitted["route"] or evidence != admitted["route_evidence"]:
            raise ValueError("mixed V17 Sol route or evidence")
        measurements[str(row["cell_id"])] = {
            "condition": row["condition"],
            "answer": admitted["answer"],
            "provenance": {
                "receipt_sha256": sha256(admitted["receipt"]),
                "raw_response_sha256": sha256(admitted["final"]),
                "endpoint": "sol_later",
                "thread_id": key[0],
                "session_id": key[1],
            },
        }
    if set(entries) != {str(row["cell_id"]) for row in rows} or len(measurements) != 48 or len(identities) != 48 or route is None or evidence is None:
        raise ValueError("V17 Sol fresh receipt geometry is incomplete")
    v4._frozen_route(route, evidence, base._load_v3(), require_unexpired=False)
    return measurements


def _runtime(resolution: Mapping[str, Any]) -> ModuleType:
    runtime = _load_exact(V16_EXECUTOR, V16_EXECUTOR_SHA256, V16_EXECUTOR_COMMIT, "_v17_v16_runtime")
    runtime.STUDY_ID = STUDY_ID
    runtime.CORE = CORE
    runtime.CORE_COMMIT = CORE_COMMIT
    runtime.MAX_CONCURRENCY = MAX_CONCURRENCY
    runtime._resolution = _resolution
    runtime._execution_schedule = _execution_schedule
    runtime._source_roots = _source_roots
    runtime._sol_rows = lambda value: _sol_rows(runtime, value)
    inherited_sol_runtime = runtime._sol_runtime

    def sol_runtime(value: Mapping[str, Any]) -> tuple[ModuleType, ModuleType, tuple[dict[str, Any], ...]]:
        lifecycle, base, rows = inherited_sol_runtime(value)
        inherited_prepared = base._prepared

        def prepared(row: Mapping[str, Any], payload: bytes, schema: bytes, target: Mapping[str, Any], route: Mapping[str, Any], evidence: Mapping[str, Any], acknowledgement: str) -> dict[str, bytes]:
            files = inherited_prepared(row, payload, schema, target, route, evidence, acknowledgement)
            metadata = json.loads(files["prepared.json"])
            source = metadata["source"]
            for key in ("v16_core_sha256", "v16_schedule_sha256", "public_result_commit", "source_result_file_sha256", "source_executor_commit", "source_executor_sha256", "schedule_sha256", "collector_sha256", "result_internal_sha256"):
                source.pop(key, None)
            source.update({
                "v17_core_sha256": value["core_sha256"],
                "v17_schedule_sha256": value["schedule_sha256"],
                "v17_native_contract_sha256": CONTRACT_SHA256,
                "result_analyzer_commit": CORE_COMMIT,
                "result_analyzer_sha256": value["core_sha256"],
                "result_analyzer_contract_sha256": CORE_CONTRACT_SHA256,
                "replay_input_commitments": {"v17_schedule": value["schedule_sha256"], "v17_core": value["core_sha256"], "v17_native_contract": CONTRACT_SHA256},
                "sol_role": "matched_train_measurement_on_v17_comparative_frozen_schedule",
            })
            if row["condition"] in {FORWARD, REVERSE}:
                target_file = json.loads(files["target-vector.json"])
                target_file["kind"] = "v17_comparative_panel_target_map"
                files["target-vector.json"] = base.canonical(target_file)
                metadata["target_vector_sha256"] = sha256(files["target-vector.json"])
            files["prepared.json"] = base.canonical(metadata)
            return files

        base._prepared = prepared
        return lifecycle, base, rows

    runtime._sol_runtime = sol_runtime
    runtime._grok_fresh_measurements = lambda value, *, output_root, acknowledgement: _grok_fresh(runtime, value, output_root=output_root, acknowledgement=acknowledgement)
    runtime._sol_fresh_measurements = lambda value, *, output_root, acknowledgement: _sol_fresh(runtime, value, output_root=output_root, acknowledgement=acknowledgement)
    return runtime


def _grok_prepare(runtime: ModuleType, resolution: Mapping[str, Any], *, output_root: Path, queue_root: Path, acknowledgement: str, route_provider: Callable[[Path], tuple[dict[str, Any], dict[str, Any]]] | None) -> dict[str, Any]:
    if Path(output_root).exists():
        raise ValueError("fresh Grok output root required")
    with runtime._grok_bound(resolution) as (lifecycle, remote, v9, _v11, _v13, _v15):
        lifecycle._disjoint(Path(output_root), REPO, Path(queue_root), *_source_roots(resolution))
        result = lifecycle.prepare_all(output_root=Path(output_root), queue_root=Path(queue_root), authorization_acknowledgement_sha256=acknowledgement, route_provider=v9._validated_route(v9.parent_stack(), remote, Path(queue_root), route_provider), normalized_root=Path(output_root).parent / ".v17-grok-normalized", materialization_root=Path(output_root).parent / ".v17-grok-materialization", frozen_successor_path=Path(output_root).parent / ".v17-grok-successor.json", hanna_csv_path=Path(output_root).parent / ".v17-grok-source.csv")
    prepared = result.get("prepared_cells", [])
    if set(prepared) != {row["cell_id"] for row in resolution["new"]} or len(prepared) != 48:
        raise ValueError("lower lifecycle did not prepare exact V17 Grok cells")
    return {"study_id": STUDY_ID, "endpoint": "grok", "prepared_cells": prepared, "logical_cells": 48, "provider_calls_made": 0, "process_launches": 0, "native_contact_count": 0, "native_contact_count_semantics": "prepared_precontact_only"}


def _sol_prepare(runtime: ModuleType, resolution: Mapping[str, Any], *, output_root: Path, queue_root: Path, acknowledgement: str, broker_factory: Callable[[Path], Any] | None) -> dict[str, Any]:
    if Path(output_root).exists():
        raise ValueError("fresh Sol output root required")
    lifecycle, base, rows = runtime._sol_runtime(resolution)
    lifecycle._disjoint(Path(output_root), REPO, Path(queue_root), *_source_roots(resolution))
    route, evidence, _v3 = base._route(Path(queue_root), broker_factory)
    Path(output_root).mkdir(parents=True)
    for row in rows:
        root = Path(output_root) / str(row["cell_id"])
        root.mkdir()
        payload = resolution["payloads"][row["cell_id"]]
        schema = base.canonical(json.loads(payload.decode("utf-8"))["response_schema"])
        for name, raw in base._prepared(row, payload, schema, row["target"], route, evidence, acknowledgement).items():
            base._write_new(root / name, raw)
    return {"study_id": STUDY_ID, "endpoint": "sol", "prepared_cells": [row["cell_id"] for row in rows], "logical_cells": 48, "provider_calls_made": 0, "process_launches": 0, "native_contact_count": 0, "native_contact_count_semantics": "prepared_precontact_only"}


def prepare_all(*, endpoint: str, output_root: Path, expected_core_sha256: str, authorization_acknowledgement_sha256: str, split_manifest: Path, hanna_csv: Path, successor_contract: Path, queue_root: Path, grok_route_provider: Callable[[Path], tuple[dict[str, Any], dict[str, Any]]] | None = None, sol_broker_factory: Callable[[Path], Any] | None = None) -> dict[str, Any]:
    """Persist exact V17 prepared cells only; this function makes zero contacts."""
    if endpoint not in ENDPOINTS:
        raise ValueError("endpoint must be grok or sol")
    resolution = _resolution(split_manifest=Path(split_manifest), hanna_csv=Path(hanna_csv), successor_contract=Path(successor_contract), expected_core_sha256=expected_core_sha256)
    runtime = _runtime(resolution)
    if endpoint == "grok":
        return _grok_prepare(runtime, resolution, output_root=Path(output_root), queue_root=Path(queue_root), acknowledgement=authorization_acknowledgement_sha256, route_provider=grok_route_provider)
    return _sol_prepare(runtime, resolution, output_root=Path(output_root), queue_root=Path(queue_root), acknowledgement=authorization_acknowledgement_sha256, broker_factory=sol_broker_factory)


def execute_one(*, endpoint: str, output_root: Path, expected_core_sha256: str, authorization_acknowledgement_sha256: str, split_manifest: Path, hanna_csv: Path, successor_contract: Path, queue_root: Path, cell_id: str, allow_remote: bool, grok_route_provider: Callable[[Path], tuple[dict[str, Any], dict[str, Any]]] | None = None, sol_broker_factory: Callable[[Path], Any] | None = None, grok_runner: Callable[..., Mapping[str, Any]] | None = None, call_codex: Callable[..., Any] | None = None) -> dict[str, Any]:
    if endpoint not in ENDPOINTS or allow_remote is not True:
        raise ValueError("execution requires endpoint and explicit allow_remote=True")
    resolution = _resolution(split_manifest=Path(split_manifest), hanna_csv=Path(hanna_csv), successor_contract=Path(successor_contract), expected_core_sha256=expected_core_sha256)
    runtime = _runtime(resolution)
    if cell_id not in {row["cell_id"] for row in resolution["new"]}:
        raise ValueError("unknown V17 executable cell")
    if endpoint == "grok":
        return runtime._grok_execute_one(resolution, output_root=Path(output_root), queue_root=Path(queue_root), acknowledgement=authorization_acknowledgement_sha256, cell_id=cell_id, route_provider=grok_route_provider, runner=grok_runner)
    return runtime._sol_execute(resolution, output_root=Path(output_root), queue_root=Path(queue_root), acknowledgement=authorization_acknowledgement_sha256, cell_id=cell_id, broker_factory=sol_broker_factory, call_codex=call_codex)


def execute_wave(*, endpoint: str, output_root: Path, expected_core_sha256: str, authorization_acknowledgement_sha256: str, split_manifest: Path, hanna_csv: Path, successor_contract: Path, queue_root: Path, allow_remote: bool, grok_route_provider: Callable[[Path], tuple[dict[str, Any], dict[str, Any]]] | None = None, sol_broker_factory: Callable[[Path], Any] | None = None, grok_runner: Callable[..., Mapping[str, Any]] | None = None, call_codex: Callable[..., Any] | None = None) -> list[dict[str, Any]]:
    if endpoint not in ENDPOINTS or allow_remote is not True:
        raise ValueError("execution requires endpoint and explicit allow_remote=True")
    resolution = _resolution(split_manifest=Path(split_manifest), hanna_csv=Path(hanna_csv), successor_contract=Path(successor_contract), expected_core_sha256=expected_core_sha256)
    runtime = _runtime(resolution)
    if endpoint == "grok":
        outcomes = runtime._grok_execute_wave(resolution, output_root=Path(output_root), queue_root=Path(queue_root), acknowledgement=authorization_acknowledgement_sha256, route_provider=grok_route_provider, runner=grok_runner)
        success = "provisional_scoring_received"
    else:
        outcomes = runtime._sol_execute_wave(resolution, output_root=Path(output_root), queue_root=Path(queue_root), acknowledgement=authorization_acknowledgement_sha256, broker_factory=sol_broker_factory, call_codex=call_codex)
        success = "local_codex_lifecycle_received_native_contact_unproven"
    if (len(outcomes) != 48
            or {row.get("cell_id") for row in outcomes} != set(resolution["payloads"])
            or any(row.get("state") != success for row in outcomes)):
        raise ValueError("V17 wave has incomplete or terminal non-success outcomes; preserve receipts and do not resend")
    return outcomes


def _fresh(runtime: ModuleType, resolution: Mapping[str, Any], *, endpoint: str, output_root: Path, acknowledgement: str) -> dict[str, dict[str, Any]]:
    if endpoint == "grok":
        value = runtime._grok_fresh_measurements(resolution, output_root=Path(output_root), acknowledgement=acknowledgement)
    else:
        value = runtime._sol_fresh_measurements(resolution, output_root=Path(output_root), acknowledgement=acknowledgement)
    if len(value) != 48:
        raise ValueError("V17 fresh receipt geometry is incomplete")
    endpoint_label = "grok_primary" if endpoint == "grok" else "sol_later"
    for cell_id, measurement in value.items():
        row = next(row for row in resolution["new"] if row["cell_id"] == cell_id)
        provenance = measurement.get("provenance")
        if not isinstance(provenance, dict) or provenance.get("endpoint") != endpoint_label:
            raise ValueError("V17 endpoint provenance is incomplete")
        provenance.update({"cell_id": cell_id, "payload_sha256": row["payload_sha256"], "v17_schedule_sha256": resolution["schedule_sha256"]})
    return value


def report(*, endpoint: str, output_root: Path, expected_core_sha256: str, authorization_acknowledgement_sha256: str, split_manifest: Path, hanna_csv: Path, successor_contract: Path, v15_root: Path, v15_acknowledgement_sha256: str) -> dict[str, Any]:
    """Re-admit native receipts and independently rederive the V17 schedule."""
    if endpoint not in ENDPOINTS:
        raise ValueError("endpoint must be grok or sol")
    resolution = _resolution(split_manifest=Path(split_manifest), hanna_csv=Path(hanna_csv), successor_contract=Path(successor_contract), expected_core_sha256=expected_core_sha256)
    runtime = _runtime(resolution)
    fresh = _fresh(runtime, resolution, endpoint=endpoint, output_root=Path(output_root), acknowledgement=authorization_acknowledgement_sha256)
    if endpoint == "grok":
        reused = runtime._v15_grok_reuse(resolution, v15_root=Path(v15_root), acknowledgement=v15_acknowledgement_sha256)
        endpoint_label = "grok_primary"
    else:
        reused = runtime._v15_sol_reuse(resolution, v15_root=Path(v15_root), acknowledgement=v15_acknowledgement_sha256)
        endpoint_label = "sol_later"
    measurements = {**reused, **fresh}
    if len(reused) != 12 or len(measurements) != 60 or set(reused) & set(fresh):
        raise ValueError("V17 receipt measurement inventory drifted")
    for cell_id, row in ((row["cell_id"], row) for row in resolution["reused"]):
        provenance = measurements[cell_id].get("provenance")
        if not isinstance(provenance, dict) or provenance.get("endpoint") != endpoint_label:
            raise ValueError("V17 reused receipt provenance is incomplete")
        provenance.update({"cell_id": cell_id, "payload_sha256": row["payload_sha256"], "v17_schedule_sha256": resolution["schedule_sha256"], "historical_v15_direct": True})
    analysis = resolution["core"].analyze(resolution["schedule"], measurements, expected_endpoint=endpoint_label, **resolution["source_paths"])
    return {
        "format_version": 1, "study_id": STUDY_ID,
        "kind": "receipt_replayed_v17_comparative_train_replication_endpoint_report",
        "endpoint": endpoint_label, "native_endpoint_contact_cardinality": "unproven",
        "v17_core_commit": CORE_COMMIT, "v17_core_sha256": resolution["core_sha256"],
        "v17_core_contract_sha256": CORE_CONTRACT_SHA256,
        "v17_native_contract_sha256": CONTRACT_SHA256,
        "v17_schedule_sha256": resolution["schedule_sha256"],
        "runtime": {"v16_executor_commit": V16_EXECUTOR_COMMIT, "v16_executor_sha256": V16_EXECUTOR_SHA256},
        "fresh_native_cell_count": 48, "historical_v15_direct_reuse_count": 12,
        "measurement_provenance": {
            "fresh_endpoint": endpoint_label,
            "fresh_acknowledgement_sha256": authorization_acknowledgement_sha256,
            "v15_acknowledgement_sha256": v15_acknowledgement_sha256,
            "cells": {cell_id: measurements[cell_id]["provenance"] for cell_id in sorted(measurements)},
        },
        "analysis": analysis, "authority": resolution["schedule"]["authority"],
    }


if __name__ == "__main__":
    raise SystemExit("Use the callable endpoint API; execution needs an explicit reviewed invocation.")
