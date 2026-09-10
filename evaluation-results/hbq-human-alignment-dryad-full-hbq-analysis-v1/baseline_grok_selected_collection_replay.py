"""Read-only assembly of the selected Dryad Grok collection after ordinal 88 recovery."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import math
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from types import ModuleType
from typing import Any

ROOT = Path(__file__).resolve().parent
COMPOSITE = ROOT / "baseline_composite_admission_v5.py"
SUFFIX = ROOT / "baseline_grok_v5_suffix.py"
RECOVERY = ROOT / "baseline_grok_selected_recovery.py"
COMPOSITE_SHA256 = "efd33ba0fcce7ae8c64a9aea280830998cb974c0250a411d657304a2fd0c50f6"
SUFFIX_SHA256 = "eab249cbdaa43cdb7f89364b97079000eda7b71717693711cda1de3de66a2b75"
RECOVERY_SHA256 = "687a60bcdd26227b3bcb6ae5081f3357bceb84b4b29312653617ef3d36887399"
QUESTION_COUNT = 178
STORY_COUNT = 100
LOGICAL_COUNT = 2300
NATIVE_COUNT = 2299
RECOVERED_ORDINAL = 70
OLD_V5_ORDINALS = [*range(81, 88), *range(89, 92)]
NEW_ORDINALS = [88, *range(92, 1611), *range(4049, 4739)]
_HASH = re.compile(r"[0-9a-f]{64}\Z")


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")


def _require(value: bool, message: str) -> None:
    if not value:
        raise ValueError(message)


def _digest(value: Any, label: str) -> str:
    _require(isinstance(value, str) and _HASH.fullmatch(value) is not None, f"{label} must be a lowercase SHA-256")
    return value


def _read(path: Path | str, expected: str, label: str) -> bytes:
    checked = Path(path).resolve()
    _require(checked.is_file(), f"{label} is missing")
    raw = checked.read_bytes()
    _require(_sha(raw) == _digest(expected, label + " hash") and checked.read_bytes() == raw, f"{label} drifted")
    return raw


def _json(raw: bytes, label: str) -> Any:
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"{label} is malformed") from error


def _module(path: Path, expected: str, label: str) -> ModuleType:
    raw = _read(path, expected, label)
    spec = importlib.util.spec_from_file_location("_dryad_selected_collection_" + label.replace(" ", "_"), path)
    _require(spec is not None and spec.loader is not None, f"{label} cannot load")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    _require(path.read_bytes() == raw, f"{label} changed while loading")
    return module


def source_for_ordinal(ordinal: int) -> str:
    """Name the immutable replay root responsible for one selected ordinal."""
    _require(type(ordinal) is int, "selected ordinal differs")
    if 1 <= ordinal <= 80:
        return "original_v4_prefix"
    if ordinal in OLD_V5_ORDINALS:
        return "old_v5"
    if ordinal in NEW_ORDINALS:
        return "recovery"
    raise ValueError("selected ordinal is outside the collection")


def _identity(value: Any, label: str) -> dict[str, str]:
    fields = {"request_id_hash", "session_id_hash"}
    _require(isinstance(value, Mapping) and set(value) in (fields, fields | {"observed_turns"}), f"{label} identity differs")
    result = {key: value[key] for key in ("request_id_hash", "session_id_hash")}
    _require(all(isinstance(item, str) and _HASH.fullmatch(item) for item in result.values()), f"{label} identity differs")
    if "observed_turns" in value:
        _require(type(value["observed_turns"]) is int and value["observed_turns"] >= 1, f"{label} identity differs")
    return result


def _unique(identities: Sequence[Mapping[str, Any]]) -> list[dict[str, str]]:
    result = [_identity(item, "collection") for item in identities]
    requests = [item["request_id_hash"] for item in result]
    sessions = [item["session_id_hash"] for item in result]
    _require(len(requests) == len(set(requests)) and len(sessions) == len(set(sessions)), "collection native identity duplicate")
    return result


def _verdicts(value: Any, question_ids: Sequence[str], label: str) -> list[dict[str, Any]]:
    _require(isinstance(value, list) and len(value) == QUESTION_COUNT, f"{label} verdict count differs")
    result = [dict(item) for item in value if isinstance(item, Mapping)]
    _require(len(result) == QUESTION_COUNT and [item.get("question_id") for item in result] == list(question_ids),
             f"{label} criterion order differs")
    normalized = [{"question_id": item["question_id"], "verdict": item.get("verdict")} for item in result]
    _require(all(isinstance(item["verdict"], str) for item in normalized), f"{label} verdict differs")
    return normalized


def _score(runtime: Any, *, verdicts: Sequence[Mapping[str, Any]], artifact_id: str) -> tuple[float | int, float | int]:
    result = runtime.core.score_bundle(runtime.modules, runtime.bundle, list(verdicts), artifact_id=artifact_id, task_contract=None)
    final = result.get("final_score") if isinstance(result, Mapping) else None
    observed, coverage = (final.get("observed") if isinstance(final, Mapping) else None), result.get("coverage") if isinstance(result, Mapping) else None
    _require(type(observed) in (int, float) and math.isfinite(observed) and 0 <= observed <= 100
             and type(coverage) in (int, float) and math.isfinite(coverage) and 0 <= coverage <= 1,
             "canonical collection score differs")
    return observed, coverage


def _source_commitment(record: Mapping[str, Any]) -> dict[str, Any]:
    result = {"sha256": record.get("source_sha256"), "bytes": record.get("source_bytes")}
    _require(isinstance(result["sha256"], str) and _HASH.fullmatch(result["sha256"])
             and type(result["bytes"]) is int and result["bytes"] >= 0, "story source commitment differs")
    return result


def _terminal_commitment(parent: Any, root: Path, ordinal: int) -> dict[str, Any]:
    raw = parent._attempt_path(root, ordinal, "terminal.json").read_bytes()
    return {"ordinal": ordinal, "source": source_for_ordinal(ordinal), "terminal_sha256": _sha(raw)}


def _record(*, record: Mapping[str, Any], ordinals: Sequence[int], verdicts: Sequence[Mapping[str, Any]], runtime: Any,
            provenance: str, replay_input_commitments: Mapping[str, Any]) -> dict[str, Any]:
    artifact_id = record.get("opaque_story_id")
    _require(isinstance(artifact_id, str) and artifact_id, "opaque story identity differs")
    _require(isinstance(replay_input_commitments, Mapping), "replay input commitments differ")
    score, coverage = _score(runtime, verdicts=verdicts, artifact_id=artifact_id)
    return {"pass_id": record["pass_id"], "partition": record["partition"], "opaque_story_id": artifact_id,
            "source": _source_commitment(record), "ordinals": list(ordinals), "provenance": provenance,
            "replay_input_commitments": dict(replay_input_commitments), "verdict_rows": list(verdicts),
            "verdicts_sha256": _sha(_canonical(list(verdicts))), "score": score, "coverage": coverage}


def _load_recovery(root: Path, recovery: Any, expected_controller_sha256: str, expected_manifest_sha256: str) -> tuple[dict[str, Any], bytes, Any, dict[str, Any], set[int], list[dict[str, str]]]:
    manifest_raw = _read(root / "recovery-manifest.json", expected_manifest_sha256, "Recovery manifest")
    manifest = _json(manifest_raw, "Recovery manifest")
    _require(isinstance(manifest, Mapping) and manifest.get("controller_sha256") == expected_controller_sha256,
             "recovery controller binding differs")
    _require(_sha(RECOVERY.read_bytes()) == expected_controller_sha256, "recovery controller source differs")
    parent = recovery._load_parent(manifest["parent_source"]["sha256"])
    epoch, epoch_raw, _plan_root, _requests = recovery._inner(parent, root, manifest["inner_epoch"]["sha256"])
    recovery._source_guard(parent, manifest, epoch_raw)
    completed, identities = recovery._validated_replay_chain(root, parent, manifest, manifest_raw, epoch)
    _require(set(NEW_ORDINALS) <= completed, "recovery selected ordinals require replay")
    return dict(manifest), manifest_raw, parent, dict(epoch), completed, _unique(identities)


def read_selected_collection(
    *, plan_root: Path | str, predecessor_path: Path | str, old_suffix_root: Path | str, recovery_root: Path | str,
    expected_plan_sha256: str, expected_predecessor_sha256: str, expected_old_epoch_sha256: str,
    expected_suffix_source_sha256: str, expected_recovery_controller_sha256: str,
    expected_recovery_manifest_sha256: str, approved_v4_routes: Mapping[str, Any], approved_v5_routes: Mapping[str, Any],
) -> dict[str, Any]:
    """Replay the complete selected collection without admission, dispatch, or source disclosure."""
    reader_raw = Path(__file__).read_bytes()
    _require(expected_suffix_source_sha256 == SUFFIX_SHA256 and expected_recovery_controller_sha256 == RECOVERY_SHA256,
             "frozen collection helper binding differs")
    composite = _module(COMPOSITE, COMPOSITE_SHA256, "composite helper")
    suffix = _module(SUFFIX, expected_suffix_source_sha256, "suffix helper")
    recovery = _module(RECOVERY, expected_recovery_controller_sha256, "recovery helper")
    plan_root, old_root, new_root = Path(plan_root).resolve(), Path(old_suffix_root).resolve(), Path(recovery_root).resolve()
    _require(plan_root.is_dir() and old_root.is_dir() and new_root.is_dir(), "collection root differs")
    _predecessor_raw, predecessor = composite._predecessor(predecessor_path, expected_predecessor_sha256)
    context = composite._actual_replay_context(suffix_root=old_root, plan_root=plan_root,
                                                expected_epoch_sha256=expected_old_epoch_sha256,
                                                expected_suffix_source_sha256=expected_suffix_source_sha256,
                                                predecessor=predecessor)
    manifest, _manifest_raw, new_parent, new_epoch, replayed, new_identities = _load_recovery(
        new_root, recovery, expected_recovery_controller_sha256, expected_recovery_manifest_sha256)
    _require(new_parent.__file__ == suffix.__file__ and new_epoch["plan_sha256"] == expected_plan_sha256,
             "recovery suffix or plan differs")
    plan, _raw, passes, pass_index, question_ids = composite._plan(plan_root, expected_plan_sha256)
    requests_by_ordinal = {item["ordinal"]: item for item in plan["requests"]}
    schedule = context.epoch["selected_request_ordinals"]
    _require(schedule == [item["ordinal"] for item in plan["requests"] if item.get("ordinal") in schedule]
             and len(schedule) == LOGICAL_COUNT and schedule[0] == 1 and schedule[-1] == 4738,
             "selected request schedule differs")
    records_by_pass = {item["pass_id"]: item for item in passes}
    selected = [records_by_pass[item["pass_id"]] for item in plan["passes"] if item.get("pass_id") in records_by_pass and item.get("pass_id") in {
        request.get("pass_id") for request in plan["requests"] if request.get("ordinal") in schedule
    }]
    _require(len(selected) == STORY_COUNT, "selected pass inventory differs")
    runtime = context.suffix._runtime_from_epoch(context.epoch)
    new_runtime = new_parent._runtime_from_epoch(new_epoch)
    _require(new_runtime.transport_sha256 == runtime.transport_sha256, "recovery runtime transport differs")
    identities: list[dict[str, str]] = []
    rows: list[dict[str, Any]] = []
    for record in selected[:3]:
        run_root = next(item["run_root"] for item in context.old_passes if item["pass_id"] == record["pass_id"])
        replay = composite._actual_old_admit(context, plan_root=plan_root, pass_record=record, run_root=Path(run_root), approved_v4_routes=approved_v4_routes)
        verdicts = _verdicts(replay.get("verdicts"), question_ids, "old prefix")
        identities.extend(_identity(item, "old prefix") for item in replay.get("native_identities", []))
        ordinal_rows = [item["ordinal"] for item in plan["requests"] if item.get("pass_id") == record["pass_id"]]
        rows.append(_record(record=record, ordinals=ordinal_rows, verdicts=verdicts, runtime=runtime,
                            provenance="original_v4_prefix", replay_input_commitments={
                                "run_manifest_sha256": replay["run_manifest_sha256"],
                                "checkpoint_head_sha256": replay["checkpoint_head_sha256"],
                            }))
    mixed = selected[3]
    recovered = composite._load_module(Path(context.epoch["recovered_study_source"]["path"]), context.epoch["recovered_study_source"]["sha256"], "recovered study")
    prefix = recovered.admit_prefix(context.epoch["old_prefix_run_root"], source=composite._measurement_source(plan_root, mixed), batch_size=8,
                                    approved_routes=dict(approved_v4_routes), expected_batches=11,
                                    expected_recovered_manifest_sha256=context.epoch["recovered_study_manifest"]["sha256"],
                                    expected_adoption_sha256=context.epoch["recovery_adoption_sha256"],
                                    expected_amendment_sha256=context.epoch["recovery_amendment_sha256"], runtime=context.old_runtime)
    mixed_verdicts = list(prefix["verdicts"])
    identities.extend(_identity(item, "mixed prefix") for item in prefix["native_identities"])
    mixed_terminals: list[dict[str, Any]] = []
    for ordinal in range(81, 93):
        source = source_for_ordinal(ordinal)
        parent, root, epoch, replay_runtime = ((context.suffix, old_root, context.epoch, runtime) if source == "old_v5"
                                               else (new_parent, new_root, new_epoch, new_runtime))
        request = requests_by_ordinal[ordinal]
        verdicts, identity = parent._replay_suffix_terminal(root=root, epoch_sha256=expected_old_epoch_sha256 if source == "old_v5" else manifest["inner_epoch"]["sha256"],
            epoch=epoch, runtime=replay_runtime, plan_root=plan_root, passed=pass_index[request["pass_id"]], row=request, approved_v5_routes=approved_v5_routes)
        mixed_verdicts.extend(verdicts)
        identities.append(_identity(identity, "mixed suffix"))
        mixed_terminals.append(_terminal_commitment(parent, root, ordinal))
    rows.append(_record(record=mixed, ordinals=list(range(70, 93)), verdicts=_verdicts(mixed_verdicts, question_ids, "mixed pass"),
                        runtime=runtime, provenance="v4_recovered70_old_v5_replacement88", replay_input_commitments={
                            "prefix_run_manifest_sha256": prefix["run_manifest_sha256"],
                            "prefix_checkpoint_head_sha256": prefix["checkpoint_head_sha256"],
                            "recovered_manifest_sha256": prefix["recovered_manifest_sha256"],
                            "terminals": mixed_terminals,
                        }))
    for record in selected[4:]:
        verdicts: list[dict[str, Any]] = []
        terminals: list[dict[str, Any]] = []
        requests = [item for item in plan["requests"] if item.get("pass_id") == record["pass_id"]]
        requests.sort(key=lambda item: item["ordinal"])
        for request in requests:
            ordinal = request["ordinal"]
            _require(ordinal in NEW_ORDINALS and ordinal in replayed, "new selected request requires recovery replay")
            batch, identity = new_parent._replay_suffix_terminal(root=new_root, epoch_sha256=manifest["inner_epoch"]["sha256"], epoch=new_epoch,
                runtime=new_runtime, plan_root=plan_root, passed=pass_index[record["pass_id"]], row=request, approved_v5_routes=approved_v5_routes)
            verdicts.extend(batch)
            identities.append(_identity(identity, "recovery suffix"))
            terminals.append(_terminal_commitment(new_parent, new_root, ordinal))
        rows.append(_record(record=record, ordinals=[item["ordinal"] for item in requests],
                            verdicts=_verdicts(verdicts, question_ids, "recovery pass"), runtime=new_runtime,
                            provenance="recovery", replay_input_commitments={"terminals": terminals}))
    all_identities = _unique(identities)
    _require(len(rows) == STORY_COUNT and len(all_identities) == NATIVE_COUNT and len(new_identities) == len(NEW_ORDINALS),
             "collection cardinality differs")
    _require(Path(__file__).read_bytes() == reader_raw, "collection reader source drifted")
    coverage_failures = [row["pass_id"] for row in rows if row["coverage"] < 0.88]
    return {"schema_version": 1, "evidence_class": "selected100_grok_collection_replay_only", "counts": {"stories": STORY_COUNT,
            "logical_requests": LOGICAL_COUNT, "native_requests": NATIVE_COUNT, "study_recovered_requests": 1,
            "criterion_verdicts": STORY_COUNT * QUESTION_COUNT}, "recovered_ordinals": [RECOVERED_ORDINAL],
            "input_commitments": {"reader_sha256": _sha(reader_raw), "plan_sha256": expected_plan_sha256,
                                  "predecessor_sha256": expected_predecessor_sha256,
                                  "old_suffix_epoch_sha256": expected_old_epoch_sha256,
                                  "selected_schedule_sha256": context.epoch["selected_schedule"]["sha256"],
                                  "selected_schedule_source_sha256": context.epoch["selected_schedule_source"]["sha256"],
                                  "composite_helper_sha256": COMPOSITE_SHA256, "suffix_helper_sha256": SUFFIX_SHA256,
                                  "recovery_controller_sha256": expected_recovery_controller_sha256,
                                  "recovery_manifest_sha256": expected_recovery_manifest_sha256,
                                  "recovery_inner_epoch_sha256": manifest["inner_epoch"]["sha256"]},
            "coverage_failures": coverage_failures, "full_study_admitted": False, "provider_calls_made": 0,
            "native_identities": all_identities,
            "native_identity_commitment_sha256": _sha(_canonical(all_identities)), "rows": rows}
