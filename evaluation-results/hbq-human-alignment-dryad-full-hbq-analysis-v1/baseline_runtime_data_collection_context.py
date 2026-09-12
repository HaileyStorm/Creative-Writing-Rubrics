"""Explicit runtime-data context for provider-free Dryad replay admission."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from collections.abc import Mapping
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

ROOT = Path(__file__).resolve().parent
V4_DATA_LOADER = ROOT / "baseline_runtime_data_snapshot_v4.py"
V4_DATA_LOADER_SHA256 = (
    "7bc63e52688d7b0f4546fe3d8681b7e446ea5b6ddc2c20c7ae6f05c6a0199513"
)
V5_DATA_LOADER = ROOT / "baseline_runtime_data_snapshot.py"
V5_DATA_LOADER_SHA256 = (
    "eb068749b2483d4b8ca480e5e57865692b89518fe924848f57d324574d167b0c"
)
NATIVE_DATA_ADMISSION = ROOT / "baseline_native_data_admission.py"
NATIVE_DATA_ADMISSION_SHA256 = (
    "719dd0af186f38bdeff2ee08cf9b90275003c28cd08b1c7abd246882f585b366"
)


def _hash(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _descriptor(
    value: Any, *, path: Path, expected: str | None, label: str
) -> dict[str, str]:
    _require(
        isinstance(value, Mapping) and set(value) == {"path", "sha256"},
        f"{label} binding differs",
    )
    actual = Path(value["path"]).resolve()
    supplied = value["sha256"]
    _require(
        actual == path.resolve() and isinstance(supplied, str) and len(supplied) == 64,
        f"{label} binding differs",
    )
    if expected is not None:
        _require(supplied == expected, f"{label} binding differs")
    try:
        raw = actual.read_bytes()
    except OSError as error:
        raise ValueError(f"{label} source missing") from error
    _require(_hash(raw) == supplied, f"{label} source differs")
    return {"path": str(actual), "sha256": supplied}


def _sources(value: Any) -> dict[str, dict[str, str]]:
    _require(isinstance(value, Mapping), "runtime-data source bindings differ")
    required = {"runtime_data_snapshot_v4", "runtime_data_snapshot_v5"}
    optional = {"native_data_admission", "recovered_data_admission"}
    _require(
        set(value).issuperset(required) and set(value).issubset(required | optional),
        "runtime-data source bindings differ",
    )
    bindings = {
        "runtime_data_snapshot_v4": _descriptor(
            value["runtime_data_snapshot_v4"],
            path=V4_DATA_LOADER,
            expected=V4_DATA_LOADER_SHA256,
            label="V4 runtime-data loader",
        ),
        "runtime_data_snapshot_v5": _descriptor(
            value["runtime_data_snapshot_v5"],
            path=V5_DATA_LOADER,
            expected=V5_DATA_LOADER_SHA256,
            label="V5 runtime-data loader",
        ),
    }
    if "native_data_admission" in value:
        bindings["native_data_admission"] = _descriptor(
            value["native_data_admission"],
            path=NATIVE_DATA_ADMISSION,
            expected=NATIVE_DATA_ADMISSION_SHA256,
            label="native data admission",
        )
    if "recovered_data_admission" in value:
        bindings["recovered_data_admission"] = _descriptor(
            value["recovered_data_admission"],
            path=ROOT / "baseline_recovered_data_admission.py",
            expected=None,
            label="recovered data admission",
        )
    return bindings


def _load_bound_module(descriptor: Mapping[str, str], label: str) -> ModuleType:
    path = Path(descriptor["path"])
    raw = path.read_bytes()
    _require(_hash(raw) == descriptor["sha256"], f"{label} source differs")
    spec = importlib.util.spec_from_file_location(
        "_dryad_runtime_data_" + _hash(raw)[:16], path
    )
    _require(spec is not None and spec.loader is not None, f"{label} cannot load")
    previous = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = previous
    _require(path.read_bytes() == raw, f"{label} changed while loading")
    return module


def _verify_sources(bindings: Mapping[str, Mapping[str, str]]) -> None:
    for name, descriptor in bindings.items():
        raw = Path(descriptor["path"]).read_bytes()
        _require(
            _hash(raw) == descriptor["sha256"],
            f"{name} source changed during admission",
        )


def _snapshot_descriptor(
    epoch_path: Path, epoch_sha256: str, runtime: Any
) -> dict[str, Any]:
    provenance = getattr(runtime, "provenance", None)
    _require(isinstance(provenance, Mapping), "runtime provenance differs")
    data = provenance.get("data")
    _require(
        isinstance(data, Mapping)
        and isinstance(data.get("schema_pins"), list)
        and data["schema_pins"],
        "runtime schema provenance differs",
    )
    return {
        "epoch": {"path": str(epoch_path), "sha256": epoch_sha256},
        "schema": dict(data["schema_pins"][0]),
    }


def build_snapshot_replay_context(
    *,
    suffix_root: Path,
    plan_root: Path,
    expected_epoch_sha256: str,
    expected_suffix_source_sha256: str,
    predecessor: Mapping[str, Any],
    snapshot_manifest_path: Path,
    expected_snapshot_manifest_sha256: str,
    source_bindings: Mapping[str, Any],
) -> Any:
    """Bind frozen replay evidence to explicit V4/V5 historical-schema runtimes."""
    bindings = _sources(source_bindings)
    root = Path(suffix_root).resolve()
    epoch_path = root / "suffix-epoch.json"
    epoch_raw = epoch_path.read_bytes()
    _require(_hash(epoch_raw) == expected_epoch_sha256, "Suffix epoch drifted")
    epoch_value = json.loads(epoch_raw.decode("utf-8"))
    _require(
        isinstance(epoch_value, Mapping)
        and isinstance(epoch_value.get("executor_source"), Mapping),
        "Suffix epoch source binding differs",
    )
    executor = epoch_value["executor_source"]
    _require(
        executor.get("sha256") == expected_suffix_source_sha256,
        "Suffix source anchor differs",
    )
    suffix = _load_bound_module(
        {
            "path": str(Path(executor.get("path"))),
            "sha256": expected_suffix_source_sha256,
        },
        "Suffix executor",
    )
    epoch, _ = suffix._load_epoch(root, expected_epoch_sha256)
    resolved_plan, old_root, prefix_root, _requests = suffix._epoch_integrity(
        root, epoch
    )
    suffix._require(
        resolved_plan == Path(plan_root).resolve(), "Suffix epoch plan root differs"
    )
    prefix_raw = suffix._read(
        epoch["old_prefix_manifest"]["path"],
        epoch["old_prefix_manifest"]["sha256"],
        "Old prefix manifest",
    )
    prefix = suffix._json(prefix_raw, "Old prefix manifest")
    suffix._require(
        isinstance(prefix, Mapping)
        and isinstance(prefix.get("anchors"), Mapping)
        and isinstance(predecessor.get("recovery_manifest"), Mapping)
        and prefix["anchors"].get("grok51_manifest_sha256")
        == predecessor["recovery_manifest"].get("sha256")
        and isinstance(prefix.get("per_pass"), list)
        and len(prefix["per_pass"]) == 4,
        "Old prefix provenance differs",
    )
    old_passes: list[dict[str, str]] = []
    for item in prefix["per_pass"][:3]:
        suffix._require(
            isinstance(item, Mapping)
            and isinstance(item.get("pass_id"), str)
            and isinstance(item.get("run_root"), str)
            and item.get("checkpoint_count") == 23
            and item.get("native_records") == 23
            and item.get("study_recovered_records") == 0,
            "Old complete pass provenance differs",
        )
        old_passes.append(
            {
                "pass_id": item["pass_id"],
                "run_root": str(suffix._plain(item["run_root"], directory=True)),
            }
        )
    old_loader = _load_bound_module(
        bindings["runtime_data_snapshot_v4"], "V4 runtime-data loader"
    )
    suffix_loader = _load_bound_module(
        bindings["runtime_data_snapshot_v5"], "V5 runtime-data loader"
    )
    old_runtime = old_loader.load_old_runtime_from_epoch(
        epoch,
        snapshot_manifest_path=Path(snapshot_manifest_path),
        expected_snapshot_manifest_sha256=expected_snapshot_manifest_sha256,
    )
    suffix_runtime = suffix_loader.load_runtime_from_epoch(
        epoch,
        snapshot_manifest_path=Path(snapshot_manifest_path),
        expected_snapshot_manifest_sha256=expected_snapshot_manifest_sha256,
    )
    old_runtime.verify()
    suffix_runtime.verify()
    return SimpleNamespace(
        suffix=suffix,
        epoch=epoch,
        old_root=old_root,
        prefix_root=prefix_root,
        plan_root=Path(plan_root).resolve(),
        old_passes=old_passes,
        old_runtime=old_runtime,
        suffix_runtime=suffix_runtime,
        source_bindings=bindings,
        prefix_manifest={
            "path": epoch["old_prefix_manifest"]["path"],
            "sha256": epoch["old_prefix_manifest"]["sha256"],
        },
        prefix_anchors=dict(prefix["anchors"]),
        old_snapshot_descriptor=_snapshot_descriptor(
            epoch_path, expected_epoch_sha256, old_runtime
        ),
        suffix_snapshot_descriptor=_snapshot_descriptor(
            epoch_path, expected_epoch_sha256, suffix_runtime
        ),
    )


def admit_old_with_runtime_data(
    context: Any,
    *,
    plan_root: Path,
    pass_record: Mapping[str, Any],
    run_root: Path,
    approved_v4_routes: Mapping[str, Any],
) -> Mapping[str, Any]:
    """Replay one full frozen V4 pass through the explicit-data adapter."""
    descriptor = context.source_bindings.get("native_data_admission")
    _require(isinstance(descriptor, Mapping), "native data admission binding required")
    adapter = _load_bound_module(descriptor, "native data admission")
    source = context.suffix._source_for_pass(Path(plan_root), pass_record)
    result = adapter.admit_pass_with_runtime_data(
        run_root,
        source=source,
        batch_size=8,
        approved_routes=dict(approved_v4_routes),
        runtime=context.old_runtime,
        snapshot_descriptor=context.old_snapshot_descriptor,
    )
    _verify_sources(context.source_bindings)
    return result


def _old_prefix_identities(
    context: Any,
    *,
    plan: Mapping[str, Any],
    old: Mapping[str, Any],
    approved_v4_routes: Mapping[str, Any],
) -> list[dict[str, Any]]:
    records = context.suffix._json(
        context.suffix._read(
            context.prefix_manifest["path"],
            context.prefix_manifest["sha256"],
            "Old prefix manifest",
        ),
        "Old prefix manifest",
    )["per_pass"]
    passes = context.suffix._pass_index(plan)
    identities: list[dict[str, Any]] = []
    for record in records[:3]:
        passed = passes.get(record.get("pass_id"))
        context.suffix._require(
            isinstance(passed, Mapping), "Old native pass plan binding differs"
        )
        replay = admit_old_with_runtime_data(
            context,
            plan_root=context.plan_root,
            pass_record=passed,
            run_root=Path(record["run_root"]),
            approved_v4_routes=approved_v4_routes,
        )
        values = (
            replay.get("native_identities") if isinstance(replay, Mapping) else None
        )
        context.suffix._require(
            isinstance(values, list) and len(values) == 23,
            "Old native pass identity replay differs",
        )
        identities.extend(dict(item) for item in values if isinstance(item, Mapping))
    values = old.get("native_identities")
    context.suffix._require(
        isinstance(values, list) and len(values) == 10,
        "Recovered prefix native identity replay differs",
    )
    identities.extend(dict(item) for item in values if isinstance(item, Mapping))
    requests = [item.get("request_id_hash") for item in identities]
    sessions = [item.get("session_id_hash") for item in identities]
    context.suffix._require(
        len(identities) == 79
        and len(set(requests)) == len(requests)
        and len(set(sessions)) == len(sessions)
        and all(
            isinstance(value, str) and context.suffix._HASH.fullmatch(value)
            for value in requests + sessions
        ),
        "Old prefix native identities differ",
    )
    return identities


def admit_suffix_with_runtimes(
    context: Any,
    *,
    suffix_root: Path,
    expected_epoch_sha256: str,
    pass_id: str,
    approved_v4_routes: Mapping[str, Any],
    approved_v5_routes: Mapping[str, Any],
) -> Mapping[str, Any]:
    """Replay a mixed or V5 pass without the frozen runtime factories."""
    recovered_descriptor = context.source_bindings.get("recovered_data_admission")
    _require(
        isinstance(recovered_descriptor, Mapping),
        "recovered data admission binding required",
    )
    recovered = _load_bound_module(recovered_descriptor, "recovered data admission")
    suffix = context.suffix
    root = suffix._plain(suffix_root, directory=True)
    epoch_sha256 = suffix._sha(expected_epoch_sha256, "Suffix epoch")
    suffix._require(
        epoch_sha256 == context.old_snapshot_descriptor["epoch"]["sha256"],
        "Suffix epoch differs from runtime data",
    )
    epoch, before_epoch = suffix._load_epoch(root, epoch_sha256)
    plan_root, old_root, prefix_root, _requests = suffix._epoch_integrity(root, epoch)
    suffix._require(
        plan_root == context.plan_root and epoch == context.epoch,
        "Suffix replay context differs",
    )
    before_old, before_prefix, before_suffix = (
        suffix._inventory(old_root),
        suffix._inventory(prefix_root),
        suffix._inventory(root),
    )
    plan, _ = suffix._plan(plan_root, epoch["plan_sha256"])
    passed = suffix._pass_index(plan).get(pass_id)
    suffix._require(isinstance(passed, Mapping), "Requested mixed pass is absent")
    rows, mixed_prefix = suffix._pass_requests(plan, pass_id)
    expected_ids = [item["question"]["id"] for item in context.suffix_runtime.questions]
    suffix._require(
        len(expected_ids) == 178
        and expected_ids
        == [item["question"]["id"] for item in context.old_runtime.questions],
        "Runtime question inventories differ",
    )
    old_records = suffix._json(
        suffix._read(
            context.prefix_manifest["path"],
            context.prefix_manifest["sha256"],
            "Old prefix manifest",
        ),
        "Old prefix manifest",
    )["per_pass"]
    old_pass = suffix._pass_index(plan).get(old_records[3].get("pass_id"))
    suffix._require(
        isinstance(old_pass, Mapping), "Old recovered pass plan binding differs"
    )
    old = recovered.admit_prefix_with_runtime_data(
        prefix_root,
        source=suffix._source_for_pass(plan_root, old_pass),
        batch_size=suffix.DISPATCH_BATCH_SIZE,
        approved_routes=dict(approved_v4_routes),
        expected_batches=suffix.PREFIX_BATCHES,
        expected_recovered_manifest_sha256=epoch["recovered_study_manifest"]["sha256"],
        expected_adoption_sha256=epoch["recovery_adoption_sha256"],
        expected_amendment_sha256=epoch["recovery_amendment_sha256"],
        runtime=context.old_runtime,
        snapshot_descriptor=context.old_snapshot_descriptor,
    )
    suffix._require(
        isinstance(old, Mapping)
        and old.get("evidence_class")
        == "mixed_native_and_study_recovered_record_replay"
        and old.get("native_record_count") == 10
        and old.get("study_recovered_record_count") == 1
        and old.get("study_recovered_ordinals") == [70]
        and len(old.get("verdicts", [])) == 88
        and len(old.get("native_identities", [])) == 10,
        "Old mixed prefix admission differs",
    )
    old_prefix_identities = _old_prefix_identities(
        context, plan=plan, old=old, approved_v4_routes=approved_v4_routes
    )
    suffix_verdicts: list[dict[str, Any]] = []
    suffix_identities: list[dict[str, str]] = []
    for row in rows[suffix.PREFIX_BATCHES if mixed_prefix else 0 :]:
        suffix._require_wave_settlement(
            root, epoch_sha256=epoch_sha256, ordinal=row["ordinal"]
        )
        verdicts, identity = suffix._replay_suffix_terminal(
            root=root,
            epoch_sha256=epoch_sha256,
            epoch=epoch,
            runtime=context.suffix_runtime,
            plan_root=plan_root,
            passed=passed,
            row=row,
            approved_v5_routes=approved_v5_routes,
        )
        suffix_verdicts.extend(verdicts)
        suffix_identities.append(identity)
    combined = (
        [dict(item) for item in old["verdicts"]] if mixed_prefix else []
    ) + suffix_verdicts
    suffix._require(
        len(combined) == len(expected_ids)
        and [item.get("question_id") for item in combined] == expected_ids,
        "Pass verdict order or coverage differs",
    )
    request_ids = [item.get("request_id_hash") for item in suffix_identities]
    session_ids = [item.get("session_id_hash") for item in suffix_identities]
    suffix._require(
        len(suffix_identities) == (12 if mixed_prefix else suffix.FULL_PASS_BATCHES)
        and len(set(request_ids)) == len(request_ids)
        and len(set(session_ids)) == len(session_ids)
        and all(
            isinstance(value, str) and suffix._HASH.fullmatch(value)
            for value in request_ids + session_ids
        ),
        "Pass native identity collision",
    )
    global_v5 = suffix._completed_v5_identities(root, epoch_sha256)
    old_requests = {item["request_id_hash"] for item in old_prefix_identities}
    old_sessions = {item["session_id_hash"] for item in old_prefix_identities}
    suffix._require(
        not (old_requests & {item["request_id_hash"] for item in global_v5})
        and not (old_sessions & {item["session_id_hash"] for item in global_v5}),
        "v5 pass overlaps old native identities",
    )
    score = context.suffix_runtime.core.score_bundle(
        context.suffix_runtime.modules,
        context.suffix_runtime.bundle,
        combined,
        artifact_id=suffix._source_for_pass(plan_root, passed)["opaque_story_id"],
        task_contract=None,
    )
    observed, coverage = suffix._qualified_score(score)
    context.old_runtime.verify()
    context.suffix_runtime.verify()
    suffix._epoch_integrity(root, epoch)
    _verify_sources(context.source_bindings)
    suffix._require(
        suffix._epoch_path(root).read_bytes() == before_epoch
        and suffix._inventory(old_root) == before_old
        and suffix._inventory(prefix_root) == before_prefix
        and suffix._inventory(root) == before_suffix,
        "Read-only mixed replay changed evidence",
    )
    return {
        "pass_id": pass_id,
        "evidence_class": "mixed_v4_native_recovered70_and_v5_native_replay"
        if mixed_prefix
        else "v5_native_full_pass_replay",
        "verdicts": [
            {"question_id": item["question_id"], "verdict": item["verdict"]}
            for item in combined
        ],
        "score": observed,
        "coverage": coverage,
        "old_prefix_native_records": 79,
        "old_v4_native_records": 10 if mixed_prefix else 0,
        "old_recovered70_records": 1 if mixed_prefix else 0,
        "new_v5_native_records": len(suffix_identities),
        "native_identities": old_prefix_identities + suffix_identities,
        "provider_calls_made": 0,
    }
