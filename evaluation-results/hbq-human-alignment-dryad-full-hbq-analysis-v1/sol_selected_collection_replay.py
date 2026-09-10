"""Provider-free composition of the completed selected-100 Sol collection."""

from __future__ import annotations

import hashlib
import importlib.util
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
ADMISSION = ROOT / "sol_pass_admission.py"
REMAINING = ROOT / "sol_selected_remaining_execution.py"
RECOVERY_SHA256 = "81fd1e27fbff5f5ffc5b4c7a6a94e477705d0d59c9af8149e40fd3a58d0555fe"
ADMISSION_SHA256 = "cd8364c18cbd8a07bc18a9b4d3d0bc1102518cfbed465b9c4f4586245b8eb65d"
REMAINING_CONTROLLER_SHA256 = "244c8b02e313b19bad75de3dc26156af8c9af1eab14cd1af5679c6f13273c155"
RETAINED_COMPLETION_SHA256 = "774f3ce8b9fb41e9cbe8b9f92e41ff27aa560033d48f9a1ae7637c1310fefed6"
PRECONTACT_RECOVERY_SHA256 = "9e9e8fd23c00c4c7e4b1cf66e435543ff9a8a8fdfc2552b045510e12165f9345"
ORIGINAL_ROOT = Path(r"C:\Users\Haile\Documents\cwr-dryad-sol8-native-20260907-r1")
REPLACEMENT_ROOT = Path(r"C:\Users\Haile\Documents\sol773-replacement-execution-v1")
POST773_ROOT = Path(r"C:\Users\Haile\Documents\cwr-dryad-sol-post773-continuation-20260909-r1")
PARALLEL_ROOT = Path(r"C:\Users\Haile\Documents\cwr-dryad-sol-parallel-20260909-r1")
RECONCILIATION = Path(r"C:\Users\Haile\Documents\cwr-dryad-sol-completed-message-recovery-1328-1342-20260909-r1\reconciliation.json")
OLD_SELECTED_ROOT = Path(r"C:\Users\Haile\Documents\cwr-dryad-sol-selected100-20260909-r1")
REPLACEMENTS = (4295, 4297, 4298, 4299, 4300, 4301, 4302, 4303, 4304, 4305)
UNKNOWN_EXIT = (1328, 1333, 1335, 1336, 1337, 1338, 1339, 1340, 1341, 1342)
REMAINING_UNKNOWN_EXIT = tuple(range(4486, 4493))
SELECTED = list(range(1, 1611)) + list(range(4049, 4739))


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")


def _require(value: bool, message: str) -> None:
    if not value:
        raise ValueError(message)


def _json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_bytes().decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"{label} is malformed") from error
    _require(isinstance(value, dict), f"{label} must be an object")
    return value


def _load(path: Path, expected: str, name: str) -> Any:
    raw = path.read_bytes()
    _require(_sha(raw) == expected, f"{name} source differs")
    spec = importlib.util.spec_from_file_location(name, path)
    _require(spec is not None and spec.loader is not None, f"{name} cannot load")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    _require(path.read_bytes() == raw, f"{name} changed during load")
    return module


def _selected(schedule: Mapping[str, Any]) -> list[int]:
    ordinals = schedule.get("selected_request_ordinals")
    _require(isinstance(ordinals, list) and ordinals == SELECTED and len(ordinals) == len(set(ordinals)) == 2300,
             "selected schedule order differs")
    return list(ordinals)


def _preflight(root: Path, manifest_sha256: str, result_sha256: str, composer_sha256: str) -> tuple[dict[str, Any], dict[str, Any]]:
    _require(_sha(Path(__file__).read_bytes()) == composer_sha256, "composer source differs")
    _require(not (root / ".collect.lock").exists(), "collection lock exists")
    manifest_raw = (root / "campaign-manifest.json").read_bytes()
    _require(_sha(manifest_raw) == manifest_sha256, "campaign manifest differs")
    result_raw = (root / "collection-result.json").read_bytes()
    _require(_sha(result_raw) == result_sha256, "collection result differs")
    manifest, result = _json(root / "campaign-manifest.json", "campaign manifest"), _json(root / "collection-result.json", "collection result")
    count = result.get("logical_collection_count", result.get("recognized_logical_requests"))
    _require(result.get("state") == "collected" and count == 2300
             and result.get("logical_collection_target") == 2300 and result.get("failures") == []
             and result.get("full_study_admitted") is False, "collection result is not finished")
    return manifest, result


def _remaining_context(root: Path, manifest: Mapping[str, Any]) -> tuple[Any, Any, Any, Any, dict[str, Any], set[str], dict[str, Any], dict[str, Any]]:
    controller_sha = manifest.get("actual_controller_sha256")
    _require(controller_sha == REMAINING_CONTROLLER_SHA256 and manifest.get("driver_sha256") == RECOVERY_SHA256
             and manifest.get("completion_validator_sha256") == RETAINED_COMPLETION_SHA256
             and _sha((ROOT / "sol_retained_completion.py").read_bytes()) == RETAINED_COMPLETION_SHA256,
             "remaining campaign source differs")
    remaining = _load(REMAINING, REMAINING_CONTROLLER_SHA256, "remaining selected collector")
    _require(manifest.get("parent_manifest_sha256") == remaining.PARENT_MANIFEST_SHA256
             and manifest.get("parent_collection_result_sha256") == remaining.PARENT_RESULT_SHA256
             and manifest.get("reconciliation_sha256") == remaining.RECONCILIATION_SHA256
             and manifest.get("remaining_original_ordinals") == list(remaining.REMAINING)
             and manifest.get("counts", {}).get("recognized_prefix") == remaining.RECONCILED_PREFIX_COUNT
             and manifest.get("counts", {}).get("recognized_unknown_exit") == len(remaining.RETAINED_UNKNOWN),
             "remaining campaign binding differs")
    precontact_path = Path(manifest.get("precontact_recovery_path", ""))
    _require(precontact_path.resolve() == remaining.PRECONTACT_RECOVERY.resolve()
             and manifest.get("precontact_recovery_sha256") == PRECONTACT_RECOVERY_SHA256 == remaining.PRECONTACT_RECOVERY_SHA256
             and manifest.get("prior_precontact_failure_root") == str(remaining.R2_ROOT)
             and manifest.get("prior_precontact_failure_manifest_sha256") == remaining.R2_MANIFEST_SHA256
             and manifest.get("prior_precontact_failure_result_sha256") == remaining.R2_RESULT_SHA256,
             "remaining precontact recovery source differs")
    precontact = remaining._precontact_failure(precontact_path, PRECONTACT_RECOVERY_SHA256)
    _require(manifest.get("precontact_recovery_inventory_sha256") == remaining._sha(remaining._canonical(precontact["files"])),
             "remaining precontact recovery inventory differs")
    parent, runtime, validator, _parent_manifest, reconciliation, threads = remaining._parent_context(
        parent_root=Path(manifest["parent_campaign_root"]), reconciliation_path=Path(manifest["reconciliation_path"]),
        expected_reconciliation_sha256=manifest["reconciliation_sha256"], expected_parent_manifest_sha256=manifest["parent_manifest_sha256"])
    old = parent._load(parent.OLD, parent.OLD_SHA256, "frozen selected collector")
    schedule_raw = (root / "selected-schedule.json").read_bytes()
    _require(_sha(schedule_raw) == manifest.get("selected_schedule_sha256")
             and schedule_raw == (Path(manifest["parent_campaign_root"]) / "selected-schedule.json").read_bytes(),
             "remaining selected schedule differs")
    schedule_module = parent._load(parent.SCHEDULE, parent.SCHEDULE_SHA256, "frozen selected schedule")
    plan_root = Path(manifest["plan_root"])
    schedule = _json(root / "selected-schedule.json", "selected schedule")
    verified = schedule_module.verify_selected_schedule(descriptor=schedule, plan_root=plan_root,
                                                        expected_plan_sha256=manifest["original_plan_sha256"])
    _require(schedule_module.canonical(verified) == schedule_raw and _sha(_canonical(verified)) == manifest["selected_schedule_sha256"]
             and _sha((plan_root / "plan.json").read_bytes()) == manifest["original_plan_sha256"], "remaining plan or schedule differs")
    return remaining, parent, old, runtime, validator, reconciliation, set(threads), verified, _json(plan_root / "plan.json", "original plan")


def _phase(ordinal: int, completion_class: str | None = None) -> str:
    if ordinal <= 772:
        return "original_native_checkpoint"
    if ordinal == 773:
        return "owner_authorized_773_replacement"
    if ordinal <= 828:
        return "post773_native_continuation"
    if ordinal <= 1342:
        return "unknown_exit_retained_message" if ordinal in UNKNOWN_EXIT else "parallel_native_completion"
    if ordinal in REMAINING_UNKNOWN_EXIT or completion_class == "completed_with_unknown_exit":
        return "completed_with_unknown_exit_retained_message"
    if ordinal in REPLACEMENTS:
        return "owner_authorized_transport_replacement"
    return "selected_native_completion"


def _response_path(root: Path, parent_root: Path, request: Mapping[str, Any], pass_record: Mapping[str, Any],
                   reconciliation: Mapping[int, Mapping[str, Any]]) -> Path:
    ordinal, batch = int(request["ordinal"]), int(request["batch_number"])
    if ordinal <= 772:
        return ORIGINAL_ROOT / str(pass_record["run_path"]) / "responses" / f"batch-{batch:04d}.json"
    if ordinal == 773:
        return REPLACEMENT_ROOT / "replacement-response.json"
    if ordinal in reconciliation:
        return Path(str(reconciliation[ordinal]["native_files"]["message"]["path"]))
    if ordinal <= 828:
        return POST773_ROOT / "requests" / f"{ordinal:04d}" / "response.json"
    if ordinal <= 1342:
        return PARALLEL_ROOT / "requests" / f"{ordinal:04d}" / "response.json"
    source = OLD_SELECTED_ROOT if ordinal <= 4296 and ordinal not in REPLACEMENTS else (parent_root if ordinal <= 4506 else root)
    return source / "requests" / f"{ordinal:04d}" / "response.json"


def _completion_provenance(root: Path, ordinal: int, raw_bytes: bytes,
                           reconciliation: Mapping[int, Mapping[str, Any]]) -> tuple[str | None, bool | None]:
    if ordinal in reconciliation:
        recovery = reconciliation[ordinal]
        _require(recovery.get("process_success_proven") is False and recovery.get("process_returncode") is None
                 and recovery.get("derived_response_sha256") == _sha(raw_bytes), "unknown-exit retained message differs")
        return "completed_with_unknown_exit", False
    if ordinal < 4507:
        return None, None
    slot = root / "requests" / f"{ordinal:04d}"
    terminal = _json(slot / "terminal.json", "remaining terminal")
    record = _json(slot / "provider-record.json", "remaining provider record")
    completion_class = record.get("completion_class")
    process_success_proven = record.get("process_success_proven", True)
    _require(terminal.get("state") == completion_class and terminal.get("response_sha256") == _sha(raw_bytes)
             and type(process_success_proven) is bool, "remaining completion provenance differs")
    if completion_class == "completed_with_unknown_exit":
        _require(process_success_proven is False, "remaining unknown-exit process proof differs")
    return completion_class, process_success_proven


def _project(raw: Mapping[str, Any], request: Mapping[str, Any], *, original: bool) -> list[dict[str, str]]:
    values = raw.get("normalized_verdicts" if original else "verdicts")
    ids = request.get("question_ids")
    _require(isinstance(values, list) and isinstance(ids, list) and all(isinstance(item, Mapping) for item in values), "response verdicts differ")
    if original:
        required = {"artifact_id", "bundle_id", "confidence", "evidence", "judge_id", "note", "question_id", "run_id", "verdict"}
        _require(all(set(item) == required for item in values), "original normalized verdict record differs")
    verdicts = [{"question_id": item.get("question_id"), "verdict": item.get("verdict")} for item in values]
    _require([item["question_id"] for item in verdicts] == ids and len({item["question_id"] for item in verdicts}) == len(verdicts)
             and all(isinstance(item["verdict"], str) and item["verdict"] for item in verdicts), "response verdict identities differ")
    return verdicts


def _validate_remaining(root: Path, remaining: Any, old: Any, runtime: Any, validator: Any,
                        manifest: Mapping[str, Any], threads: set[str], plan: Mapping[str, Any]) -> set[str]:
    requests = {item.get("ordinal"): item for item in plan.get("requests", []) if isinstance(item, Mapping)}
    _require(set(requests) == set(range(1, 5429)) and len(threads) == 2068, "remaining prefix inventory differs")
    manifest_sha = remaining._sha(remaining._canonical(manifest))
    for ordinal in remaining.REMAINING:
        _require(remaining._validate_existing(root, requests[ordinal], threads, old=old, runtime=runtime,
                                              validator=validator, manifest_sha256=manifest_sha),
                 "remaining completion is absent")
    _require(len(threads) == 2300, "accepted native identity inventory differs")
    return threads


def _rows(root: Path, parent_root: Path, schedule: Mapping[str, Any], plan: Mapping[str, Any],
          additional_reconciliation: Mapping[int, Mapping[str, Any]] | None = None) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    requests = {item.get("ordinal"): dict(item) for item in plan.get("requests", []) if isinstance(item, Mapping)}
    passes = {item.get("pass_id"): dict(item) for item in plan.get("passes", []) if isinstance(item, Mapping)}
    _require(set(requests) == set(range(1, 5429)) and len(passes) == 236, "original plan inventory differs")
    reconciliation_raw = _json(RECONCILIATION, "unknown-exit reconciliation")
    recoveries = reconciliation_raw.get("recoveries")
    _require(isinstance(recoveries, list) and [item.get("ordinal") for item in recoveries if isinstance(item, Mapping)] == list(UNKNOWN_EXIT),
             "unknown-exit reconciliation differs")
    reconciliation = {int(item["ordinal"]): item for item in recoveries}
    if additional_reconciliation is not None:
        _require(not (set(reconciliation) & set(additional_reconciliation)), "unknown-exit reconciliation overlaps")
        reconciliation.update({int(ordinal): dict(record) for ordinal, record in additional_reconciliation.items()})
    source_bindings: Mapping[str, str] | None = None
    scorer: Any | None = None
    rows: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    selected_passes = schedule.get("selected_passes")
    question_ids = schedule.get("question_ids")
    _require(isinstance(selected_passes, list) and len(selected_passes) == 100 and isinstance(question_ids, list) and len(question_ids) == 178,
             "selected story inventory differs")
    for story in selected_passes:
        _require(isinstance(story, Mapping) and isinstance(story.get("pass_id"), str) and isinstance(story.get("request_ordinals"), list),
                 "selected story differs")
        pass_record = passes.get(story["pass_id"])
        ordinals = list(story["request_ordinals"])
        _require(pass_record is not None and len(ordinals) == 23 and [requests.get(ordinal, {}).get("batch_number") for ordinal in ordinals] == list(range(1, 24)),
                 "selected request batches differ")
        verdicts: list[dict[str, str]] = []
        commitments: list[dict[str, Any]] = []
        for ordinal in ordinals:
            request = requests.get(ordinal)
            _require(request is not None, "selected request is absent")
            path = _response_path(root, parent_root, request, pass_record, reconciliation)
            raw_bytes = path.read_bytes(); raw = _json(path, "canonical response")
            if ordinal <= 772:
                provider = raw.get("provider")
                metadata = provider.get("dryad_sol") if isinstance(provider, Mapping) else None
                bindings = metadata.get("source_bindings") if isinstance(metadata, Mapping) else None
                _require(isinstance(bindings, Mapping), "original source bindings differ")
                if source_bindings is None:
                    source_bindings = dict(bindings)
                    admission = _load(ADMISSION, ADMISSION_SHA256, "Sol admission scorer")
                    scorer, _base, _sol = admission._source_bindings(source_bindings)
                _require(dict(bindings) == dict(source_bindings), "original source binding drift")
            completion_class, process_success_proven = _completion_provenance(root, ordinal, raw_bytes, reconciliation)
            verdicts.extend(_project(raw, request, original=ordinal <= 772))
            commitments.append({"ordinal": ordinal, "source_class": _phase(ordinal, completion_class), "path": str(path),
                                "sha256": _sha(raw_bytes), "completion_class": completion_class,
                                "process_success_proven": process_success_proven})
        _require([item["question_id"] for item in verdicts] == question_ids and len(verdicts) == 178,
                 "story canonical question order differs")
        _require(source_bindings is not None and scorer is not None, "original source bindings are absent")
        score = scorer.core.score_bundle(scorer.modules, scorer.bundle, verdicts, artifact_id=pass_record["logical_sample_id"], task_contract=None)
        coverage, observed = score.get("coverage"), score.get("final_score", {}).get("observed")
        _require(type(coverage) in (int, float) and type(observed) in (int, float), "canonical score differs")
        row = {"pass_id": story["pass_id"], "original_opaque_story_id": pass_record["opaque_story_id"], "partition": story["partition"],
               "canonical_verdicts": verdicts, "score": observed, "coverage": coverage, "request_commitments": commitments,
               "evidence_classes": sorted({item["source_class"] for item in commitments})}
        rows.append(row)
        if coverage < .88:
            failures.append({"pass_id": story["pass_id"], "coverage": coverage, "reason": "coverage_below_0.88"})
    _require(len(rows) == 100 and sum(len(row["canonical_verdicts"]) for row in rows) == 17800, "selected aggregate differs")
    return rows, failures


def _qualification_failures(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    failures: list[dict[str, Any]] = []
    for row in rows:
        coverage = row.get("coverage")
        _require(type(coverage) in (int, float) and isinstance(row.get("pass_id"), str), "row qualification differs")
        if coverage < .88:
            failures.append({"pass_id": row["pass_id"], "coverage": coverage, "reason": "coverage_below_0.88"})
    return failures


def replay_collected(*, campaign_root: Path | str, expected_campaign_manifest_sha256: str,
                     expected_collection_result_sha256: str, expected_composer_sha256: str) -> dict[str, Any]:
    """Validate and compose only a finished, lock-free selected collection."""
    root = Path(campaign_root).resolve()
    manifest, result = _preflight(root, expected_campaign_manifest_sha256, expected_collection_result_sha256, expected_composer_sha256)
    _require(manifest.get("evidence_class") == "selected100_sol_remaining_collection_with_completed_unknown_exit_recognition_v1",
             "remaining collection manifest differs")
    remaining, _parent, old, runtime, validator, reconciliation, threads, schedule, plan = _remaining_context(root, manifest)
    recoveries = reconciliation.get("recoveries")
    _require(isinstance(recoveries, list), "remaining unknown-exit reconciliation differs")
    extra = {int(item["ordinal"]): item for item in recoveries if isinstance(item, Mapping)}
    _require(set(extra) == set(REMAINING_UNKNOWN_EXIT), "remaining unknown-exit inventory differs")
    _selected(schedule)
    threads = _validate_remaining(root, remaining, old, runtime, validator, manifest, threads, plan)
    rows, failures = _rows(root, Path(manifest["parent_campaign_root"]), schedule, plan, extra)
    _require(failures == _qualification_failures(rows), "qualification projection differs")
    unknown = [commitment for row in rows for commitment in row["request_commitments"]
               if commitment["process_success_proven"] is False]
    return {"evidence_class": "selected100_sol_provider_free_collection_replay_v1", "provider_calls": 0,
            "campaign_manifest_sha256": expected_campaign_manifest_sha256, "collection_result_sha256": expected_collection_result_sha256,
            "composer_sha256": expected_composer_sha256, "collection_result": result, "selected_requests": 2300,
            "canonical_verdicts": 17800, "accepted_native_thread_ids": sorted(threads), "full_study_admitted": False,
            "endpoint_sol_rows": rows, "qualification_failures": failures, "unknown_exit_commitments": unknown}
