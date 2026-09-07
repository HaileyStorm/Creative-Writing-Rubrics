"""Provider-free derivative copy and verification for the one-request Grok recovery."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
from collections.abc import Mapping
from pathlib import Path
from typing import Any

PLAN_SHA256 = "edeadb93c485ba227153329b5ae420de1c9d08d95e920bac0635d197fd3dbd7f"
APPROVAL_SHA256 = "c59f98ad5522335010acfc67c014c8c66d0cc92c5b9acbc49b4537fd02617621"
INCIDENT_SHA256 = "270fee2641bdcf02ef24c2b814e4e99546c767a4a5f1fa455a681d6e99db52c9"
PROBE_PATH = Path(r"C:\Users\Haile\Documents\cwr-dryad-grok51-relocation-probe-20260907-r1\probe-record.json")
PROBE_SHA256 = "db43344462145bc7802eb27cc4e64d10d5359fb20bfc49dd5cf86b8ab3bc72e2"
LAST_SETTLEMENT_SHA256 = "5578defd7d8918a5f30cca32f9a1d5996baf0de5adcf6c5e78ca57d73c14b52b"
BASE_EXECUTION_SOURCE_SHA256 = "4b4474e74d1b98210549990fdd34b44cdf36b190ead1930b3ebd661e215dfee9"

REQUEST_ORDINAL = 51
COHORT_NUMBER = 6
RUN_PATH = "runs/baseline8-v1/train/0003/dryad-01525cd0c309707489824aa4"
BATCH_NUMBER = 5
BATCH_SCHEMA_SHA256 = "1083ea9d8d810649371e654e33d6aeec1b0ba0c7a912428a013009ed8a35340a"
MUTABLE_AGGREGATE = f"{RUN_PATH}/verdicts.jsonl"
MANIFEST_NAME = "recovery-manifest.json"
FAILURE_SUFFIXES = (
    "responses/attempt-lifecycle/batch-0005/attempt-0001.settled.json",
    "responses/attempt-lifecycle/batch-0005/attempt-0001.start.json",
    "responses/batch-0005.prompt.txt.gz",
    "responses/grok-broker/batch-0005-attempt-0001/context-bindings.json",
    "responses/grok-broker/batch-0005-attempt-0001/failure-receipt.json",
    "responses/grok-broker/batch-0005-attempt-0001/outcome.json",
    "responses/grok-broker/batch-0005-attempt-0001/request.json",
    "responses/rejected/batch-0005/attempt-0001.json",
)
INCIDENT_BINDINGS = {
    "contacts/request-0051.json",
    "cohorts/0006/prepared.json",
    "cohorts/0006/review.json",
    *(f"{RUN_PATH}/{suffix}" for suffix in FAILURE_SUFFIXES[3:7]),
}


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _json(raw: bytes, label: str) -> dict[str, Any]:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            _require(key not in result, f"{label} has duplicate keys")
            result[key] = value
        return result

    try:
        result = json.loads(raw.decode("utf-8"), object_pairs_hook=pairs, parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise ValueError(f"{label} is malformed") from error
    _require(isinstance(result, dict), f"{label} must be an object")
    return result


def _absolute(path: Path | str) -> Path:
    return Path(os.path.abspath(path))


def _plain(path: Path, *, directory: bool | None = None) -> Path:
    absolute = _absolute(path)
    for candidate in (absolute, *absolute.parents):
        if not candidate.exists():
            continue
        info = candidate.lstat()
        _require(not stat.S_ISLNK(info.st_mode) and not getattr(info, "st_file_attributes", 0) & 0x400,
                 "Recovery path contains a link or reparse point")
    if directory is True:
        _require(absolute.is_dir(), "Recovery root must be an existing plain directory")
    elif directory is False:
        _require(absolute.is_file(), "Recovery artifact must be a plain file")
    return absolute


def _overlaps(first: Path, second: Path) -> bool:
    first_text, second_text = os.path.normcase(str(first)), os.path.normcase(str(second))
    try:
        return os.path.commonpath((first_text, second_text)) in {first_text, second_text}
    except ValueError:
        return False


def _outside(path: Path, *roots: Path) -> None:
    _require(all(not _overlaps(path, root) for root in roots), "Recovery paths overlap")


def _inventory(root: Path) -> dict[str, dict[str, int | str]]:
    root = _plain(root, directory=True)
    result: dict[str, dict[str, int | str]] = {}
    for directory, directories, files in os.walk(root, followlinks=False):
        base = Path(directory)
        _plain(base, directory=True)
        for name in directories:
            candidate = base / name
            info = candidate.lstat()
            _require(stat.S_ISDIR(info.st_mode) and not stat.S_ISLNK(info.st_mode)
                     and not getattr(info, "st_file_attributes", 0) & 0x400,
                     "Recovery inventory contains a link or non-directory")
        for name in files:
            candidate = base / name
            info = candidate.lstat()
            _require(stat.S_ISREG(info.st_mode) and not stat.S_ISLNK(info.st_mode)
                     and not getattr(info, "st_file_attributes", 0) & 0x400,
                     "Recovery inventory contains a link or non-file")
            relative = candidate.relative_to(root).as_posix()
            raw = candidate.read_bytes()
            result[relative] = {"bytes": len(raw), "sha256": _sha256(raw)}
    return dict(sorted(result.items()))


def _read_pinned(path: Path, expected: str, label: str) -> tuple[dict[str, Any], bytes]:
    _require(isinstance(expected, str) and len(expected) == 64, f"{label} expected hash differs")
    plain = _plain(path, directory=False)
    raw = plain.read_bytes()
    _require(_sha256(raw) == expected, f"{label} hash differs")
    _plain(plain, directory=False)
    return _json(raw, label), raw


def _plan(plan_root: Path) -> tuple[Path, dict[str, Any]]:
    root = _plain(plan_root, directory=True)
    plan, _ = _read_pinned(root / "plan.json", PLAN_SHA256, "Frozen plan")
    requests, passes = plan.get("requests"), plan.get("passes")
    _require(isinstance(requests, list) and isinstance(passes, list), "Frozen plan arrays differ")
    matching = [row for row in requests if isinstance(row, dict) and row.get("ordinal") == REQUEST_ORDINAL]
    _require(len(matching) == 1, "Frozen plan request 51 differs")
    request = matching[0]
    _require(request.get("batch_number") == BATCH_NUMBER and request.get("pass_id") == "baseline8-v1/train/0003/dryad-01525cd0c309707489824aa4"
             and request.get("schema_path") == "schemas/request-0051.json" and request.get("schema_sha256") == BATCH_SCHEMA_SHA256,
             "Frozen plan request 51 binding differs")
    _require(_sha256((root / request["schema_path"]).read_bytes()) == BATCH_SCHEMA_SHA256,
             "Frozen batch 5 schema differs")
    pass_rows = [row for row in passes if isinstance(row, dict) and row.get("run_path") == RUN_PATH]
    _require(len(pass_rows) == 1 and pass_rows[0].get("pass_id") == request["pass_id"] and pass_rows[0].get("batch_size") == 8,
             "Frozen third pass differs")
    return root, plan


def _probe() -> dict[str, str]:
    probe, _ = _read_pinned(PROBE_PATH, PROBE_SHA256, "Relocation probe")
    excluded = probe.get("excluded_failed_batch5_files")
    _require(isinstance(excluded, Mapping) and set(excluded) == set(FAILURE_SUFFIXES)
             and all(isinstance(value, str) and len(value) == 64 for value in excluded.values()),
             "Relocation probe exclusions differ")
    _require(probe.get("retained_frozen_batch5_schema_sha256") == BATCH_SCHEMA_SHA256
             and probe.get("original_unchanged_during_copy") is True
             and probe.get("native_prefix", {}).get("result") == "PASS",
             "Relocation probe binding differs")
    return dict(excluded)


def _bindings(origin: Path, plan_root: Path, approval_path: Path, incident_path: Path,
              approval_sha256: str, incident_sha256: str) -> tuple[list[str], dict[str, str]]:
    _require(approval_sha256 == APPROVAL_SHA256 and incident_sha256 == INCIDENT_SHA256,
             "Recovery authorization pin differs")
    _plan(plan_root)
    approval, _ = _read_pinned(approval_path, approval_sha256, "Recovery approval")
    _require(approval.get("logical_request_ordinal") == REQUEST_ORDINAL
             and approval.get("maximum_new_provider_attempts") == 1
             and approval.get("other_terminal_attempts_authorized") is False
             and approval.get("preserve_original_failed_attempt") is True
             and approval.get("preserve_settled_requests") == 50
             and approval.get("requires_fresh_post_revocation_zero_charge_rearm") is True
             and approval.get("requires_reviewed_implementation") is True,
             "Recovery approval differs")
    incident, _ = _read_pinned(incident_path, incident_sha256, "Recovery incident")
    _require(incident.get("logical_request_ordinal") == REQUEST_ORDINAL and incident.get("last_settled_request") == 50
             and incident.get("last_settlement_sha256") == LAST_SETTLEMENT_SHA256
             and incident.get("automatic_resend_authorized") is False,
             "Recovery incident anchor differs")
    bindings = incident.get("artifact_bindings")
    _require(isinstance(bindings, Mapping) and set(bindings) == INCIDENT_BINDINGS, "Recovery incident artifacts differ")
    for relative, expected in bindings.items():
        _require(isinstance(expected, Mapping) and set(expected) == {"bytes", "sha256"}, "Recovery incident artifact shape differs")
        actual = origin / relative
        raw = actual.read_bytes()
        _require(expected["bytes"] == len(raw) and expected["sha256"] == _sha256(raw), "Recovery incident artifact changed")

    contact = _json((origin / "contacts/request-0051.json").read_bytes(), "Original request 51")
    prepared_raw = (origin / "cohorts/0006/prepared.json").read_bytes()
    route_raw = (origin / "cohorts/0006/route.json").read_bytes()
    review_raw = (origin / "cohorts/0006/review.json").read_bytes()
    prepared, route, review = _json(prepared_raw, "Original cohort prepared"), _json(route_raw, "Original cohort route"), _json(review_raw, "Original cohort review")
    _require(contact.get("ordinal") == REQUEST_ORDINAL and contact.get("cohort_number") == COHORT_NUMBER
             and contact.get("plan_sha256") == PLAN_SHA256 and contact.get("schema_sha256") == BATCH_SCHEMA_SHA256
             and contact.get("prepared_sha256") == _sha256(prepared_raw) and contact.get("route_sha256") == _sha256(route_raw)
             and contact.get("review_sha256") == _sha256(review_raw), "Original request 51 binding differs")
    _require(prepared.get("cohort_number") == COHORT_NUMBER and prepared.get("plan_sha256") == PLAN_SHA256
             and prepared.get("previous_settlement_sha256") == LAST_SETTLEMENT_SHA256
             and prepared.get("execution_source_sha256") == BASE_EXECUTION_SOURCE_SHA256
             and prepared.get("request_ordinals") == list(range(51, 61))
             and prepared.get("route_sha256") == _sha256(route_raw)
             and isinstance(route, dict) and review.get("decision") == "approved_cohort"
             and review.get("prepared_sha256") == _sha256(prepared_raw), "Original cohort 6 binding differs")
    probe = _probe()
    for suffix, expected_sha256 in probe.items():
        failed_path = _plain(origin / RUN_PATH / suffix, directory=False)
        _require(_sha256(failed_path.read_bytes()) == expected_sha256, "Original failed batch 5 artifact changed")
    excluded = ["contacts/request-0051.json", "cohorts/0006/prepared.json", "cohorts/0006/route.json", "cohorts/0006/review.json"]
    excluded.extend(f"{RUN_PATH}/{suffix}" for suffix in probe)
    return sorted(excluded), probe


def _manifest(value: dict[str, Any]) -> bytes:
    return _canonical(value)


def _manifest_value(raw: bytes) -> dict[str, Any]:
    value = _json(raw, "Recovery manifest")
    _require(_manifest(value) == raw, "Recovery manifest is not canonical")
    required = {
        "format_version", "kind", "execution_authority", "origin_root", "derivative_root", "plan_root",
        "approval", "incident", "probe", "plan_sha256", "replacement_ordinal", "replacement_run_path",
        "replacement_batch_number", "last_settlement_sha256", "base_execution_source_sha256", "prepare_source_sha256",
        "original_files", "exact_excluded_paths", "mutable_derivative_paths", "copy",
    }
    _require(set(value) == required and value["format_version"] == 1 and value["kind"] == "grok51_derivative_copy_projection"
             and value["execution_authority"] is False and value["plan_sha256"] == PLAN_SHA256
             and value["replacement_ordinal"] == REQUEST_ORDINAL and value["replacement_run_path"] == RUN_PATH
             and value["replacement_batch_number"] == BATCH_NUMBER and value["last_settlement_sha256"] == LAST_SETTLEMENT_SHA256
             and value["base_execution_source_sha256"] == BASE_EXECUTION_SOURCE_SHA256,
             "Recovery manifest binding differs")
    return value


def _copy_state(value: dict[str, Any]) -> tuple[dict[str, dict[str, int | str]], dict[str, dict[str, int | str]]]:
    original, copied = value.get("original_files"), value.get("copy", {}).get("files")
    _require(isinstance(original, dict) and isinstance(copied, dict), "Recovery manifest file maps differ")
    excluded, mutable = value.get("exact_excluded_paths"), value.get("mutable_derivative_paths")
    _require(isinstance(excluded, list) and isinstance(mutable, list) and mutable == [MUTABLE_AGGREGATE]
             and all(isinstance(item, str) for item in excluded), "Recovery manifest exclusions differ")
    _require(set(copied) == set(original) - set(excluded) and MUTABLE_AGGREGATE in copied,
             "Recovery manifest copied inventory differs")
    _require(value["copy"].get("file_count") == len(copied) and value["copy"].get("bytes") == sum(item["bytes"] for item in copied.values())
             and value["copy"].get("files_map_sha256") == _sha256(_canonical(copied)), "Recovery manifest copy summary differs")
    return original, copied


def prepare_projection(origin_root: Path, derivative_root: Path, plan_root: Path, approval_path: Path,
                       incident_path: Path, manifest_path: Path, *, expected_approval_sha256: str,
                       expected_incident_sha256: str) -> dict[str, Any]:
    """Copy immutable predecessor evidence into a fresh derivative root; never contacts a provider."""
    origin = _plain(Path(origin_root), directory=True)
    derivative = _absolute(Path(derivative_root))
    plan = _plain(Path(plan_root), directory=True)
    approval, incident, manifest = _plain(Path(approval_path), directory=False), _plain(Path(incident_path), directory=False), _absolute(Path(manifest_path))
    _outside(derivative, origin, plan, approval, incident, manifest)
    _outside(manifest, origin, derivative)
    _require(manifest == derivative.parent / MANIFEST_NAME, "Recovery manifest must use the fixed external locator")
    _require(not derivative.exists(), "Derivative root must be new")
    _require(not manifest.exists() and manifest.parent.is_dir(), "Recovery manifest path must be new and external")
    _plain(manifest.parent, directory=True)
    excluded, _ = _bindings(origin, plan, approval, incident, expected_approval_sha256, expected_incident_sha256)
    original = _inventory(origin)
    _require(set(excluded).issubset(original), "Recovery exclusions are absent from original")
    copied = {relative: entry for relative, entry in original.items() if relative not in excluded}
    derivative.mkdir(parents=True)
    for relative in copied:
        source, target = origin / relative, derivative / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    _require(_inventory(origin) == original and _inventory(derivative) == copied,
             "Recovery copy changed source or bytes")
    source_sha256 = _sha256(Path(__file__).read_bytes())
    value = {
        "format_version": 1, "kind": "grok51_derivative_copy_projection", "execution_authority": False,
        "origin_root": str(origin), "derivative_root": str(derivative), "plan_root": str(plan),
        "approval": {"path": str(approval), "sha256": expected_approval_sha256},
        "incident": {"path": str(incident), "sha256": expected_incident_sha256},
        "probe": {"path": str(_absolute(PROBE_PATH)), "sha256": PROBE_SHA256},
        "plan_sha256": PLAN_SHA256, "replacement_ordinal": REQUEST_ORDINAL, "replacement_run_path": RUN_PATH,
        "replacement_batch_number": BATCH_NUMBER, "last_settlement_sha256": LAST_SETTLEMENT_SHA256,
        "base_execution_source_sha256": BASE_EXECUTION_SOURCE_SHA256, "prepare_source_sha256": source_sha256,
        "original_files": original, "exact_excluded_paths": excluded, "mutable_derivative_paths": [MUTABLE_AGGREGATE],
        "copy": {"file_count": len(copied), "bytes": sum(entry["bytes"] for entry in copied.values()),
                 "files_map_sha256": _sha256(_canonical(copied)), "files": copied},
    }
    raw = _manifest(value)
    manifest.write_bytes(raw)
    return {"manifest_path": str(manifest), "manifest_sha256": _sha256(raw), "origin_files": len(original),
            "copied_files": len(copied), "excluded_files": len(excluded), "provider_calls_made": 0}


def verify_projection(manifest_path: Path, expected_manifest_sha256: str, *, allow_progress: bool = False) -> dict[str, Any]:
    """Verify immutable source and copied checkpoint bytes without execution authority."""
    manifest = _plain(Path(manifest_path), directory=False)
    raw = manifest.read_bytes()
    _require(_sha256(raw) == expected_manifest_sha256, "Recovery manifest hash differs")
    value = _manifest_value(raw)
    origin, derivative, plan = _plain(Path(value["origin_root"]), directory=True), _plain(Path(value["derivative_root"]), directory=True), _plain(Path(value["plan_root"]), directory=True)
    approval, incident = _plain(Path(value["approval"]["path"]), directory=False), _plain(Path(value["incident"]["path"]), directory=False)
    _outside(manifest, origin, derivative)
    _outside(derivative, origin, plan, approval, incident)
    _require(manifest == derivative.parent / MANIFEST_NAME, "Recovery manifest locator differs")
    _require(value["prepare_source_sha256"] == _sha256(Path(__file__).read_bytes()), "Recovery helper source differs")
    _require(value["probe"] == {"path": str(_absolute(PROBE_PATH)), "sha256": PROBE_SHA256}, "Recovery probe binding differs")
    excluded, _ = _bindings(origin, plan, approval, incident, value["approval"]["sha256"], value["incident"]["sha256"])
    _require(value["exact_excluded_paths"] == excluded, "Recovery manifest exclusions differ")
    original, copied = _copy_state(value)
    _require(_inventory(origin) == original, "Original source inventory or bytes changed")
    current = _inventory(derivative)
    _require(set(copied).issubset(current), "Derivative copied inventory is incomplete")
    for relative, expected in copied.items():
        if allow_progress and relative == MUTABLE_AGGREGATE:
            continue
        _require(current[relative] == expected, "Derivative checkpoint bytes changed")
    if not allow_progress:
        _require(current == copied, "Derivative inventory changed")
    return {"status": "verified", "manifest_sha256": expected_manifest_sha256, "origin_files": len(original),
            "copied_files": len(copied), "added_derivative_files": len(set(current) - set(copied)),
            "allow_progress": allow_progress, "provider_calls_made": 0}
