"""Bounded v5-only suffix collection for the frozen Dryad batch-eight plan.

This module deliberately does not resume the v4 runner.  It starts a distinct,
hash-bound epoch at ordinal 81, retains the mixed v4/recovered prefix as
read-only evidence, and sends at most one explicitly selected v5 request per
call.  Loading or preparing an epoch has no provider authority.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import stat
import sys
import threading
import uuid
from collections.abc import Mapping, Sequence
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import ModuleType
from typing import Any

ROOT = Path(__file__).resolve().parent
REPOSITORY = ROOT.parents[1]
PLAN_SHA256 = "edeadb93c485ba227153329b5ae420de1c9d08d95e920bac0635d197fd3dbd7f"
FIRST_SUFFIX_ORDINAL = 81
LAST_ORDINAL = 5428
PREFIX_BATCHES = 11
FULL_PASS_BATCHES = 23
DISPATCH_BATCH_SIZE = 8
REVIEW_TIMEOUT_SECONDS = 300
MAX_WAVE_SIZE = 10
WAVE_EXECUTION_MODE = "ten_concurrent_grok_v5_waves"
OLD_PREFIX_NATIVE_IDENTITY_COMMITMENT_SHA256 = "9b72bae7125e6125976bf2ce37f38ad5be536c6363ed8b3d9a249d95b10d32d0"
_HASH = re.compile(r"[0-9a-f]{64}\Z")


def _hash(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")


def _require(value: bool, message: str) -> None:
    if not value:
        raise ValueError(message)


def _sha(value: Any, label: str) -> str:
    _require(isinstance(value, str) and _HASH.fullmatch(value) is not None, f"{label} must be a lowercase SHA-256")
    return value


def _plain(path: Path | str, *, directory: bool | None = None) -> Path:
    absolute = Path(os.path.abspath(path))
    for candidate in (absolute, *absolute.parents):
        try:
            info = candidate.lstat()
        except FileNotFoundError:
            continue
        _require(
            not stat.S_ISLNK(info.st_mode) and not getattr(info, "st_file_attributes", 0) & 0x400,
            "Path contains a link or reparse point",
        )
    if directory is True:
        _require(absolute.is_dir(), "Expected directory")
    if directory is False:
        _require(absolute.is_file(), "Expected file")
    return absolute


def _relative(root: Path, value: Any, *, directory: bool | None = None) -> Path:
    _require(isinstance(value, str) and value, "Relative path differs")
    candidate = Path(value)
    _require(not candidate.is_absolute() and all(part not in {".", ".."} for part in candidate.parts), "Relative path differs")
    result = _plain(root / candidate, directory=directory)
    _require(result.is_relative_to(root), "Relative path escapes its root")
    return result


def _json(raw: bytes, label: str) -> dict[str, Any]:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            _require(isinstance(key, str) and key not in result, f"{label} has duplicate keys")
            result[key] = value
        return result

    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=pairs,
                           parse_constant=lambda item: (_ for _ in ()).throw(ValueError(item)))
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise ValueError(f"{label} is malformed") from error
    _require(isinstance(value, dict), f"{label} must be an object")
    return value


def _read(path: Path | str, expected: str, label: str) -> bytes:
    checked = _plain(path, directory=False)
    raw = checked.read_bytes()
    _require(_hash(raw) == _sha(expected, label + " hash"), f"{label} hash differs")
    _require(checked.read_bytes() == raw, f"{label} changed while reading")
    return raw


def _write_new(path: Path, raw: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())


def _inventory(root: Path) -> dict[str, str]:
    checked = _plain(root, directory=True)
    paths = sorted(checked.rglob("*"))
    _require(not any(path.is_symlink() for path in paths), "Evidence root contains a link")
    return {path.relative_to(checked).as_posix(): _hash(path.read_bytes()) for path in paths if path.is_file()}


def _disjoint(*paths: Path) -> None:
    for index, left in enumerate(paths):
        for right in paths[index + 1:]:
            _require(not left.is_relative_to(right) and not right.is_relative_to(left), "Suffix roots must be disjoint")


def _load_module(path: Path, expected: str, prefix: str) -> ModuleType:
    raw = _read(path, expected, "Pinned module source")
    name = prefix + uuid.uuid4().hex
    module = ModuleType(name)
    module.__file__, module.__package__ = str(path), ""
    sys.modules[name] = module
    try:
        exec(compile(raw, str(path), "exec"), module.__dict__)  # noqa: S102 - exact locally pinned source.
    finally:
        sys.modules.pop(name, None)
    _require(path.read_bytes() == raw, "Pinned module source changed while loading")
    return module


def _time(value: Any, label: str) -> datetime:
    _require(isinstance(value, str), f"{label} must be UTC")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(f"{label} must be UTC") from error
    _require(parsed.tzinfo is not None and parsed.utcoffset() == timedelta(0), f"{label} must be UTC")
    return parsed.astimezone(timezone.utc)


def _plan(plan_root: Path, expected: str) -> tuple[dict[str, Any], bytes]:
    _require(expected == PLAN_SHA256, "Frozen baseline plan anchor differs")
    raw = _read(_relative(plan_root, "plan.json", directory=False), expected, "Frozen baseline plan")
    plan = _json(raw, "Frozen baseline plan")
    _require(
        plan.get("dispatch_batch_size") == DISPATCH_BATCH_SIZE
        and plan.get("empirical_batch_cap") is None
        and isinstance(plan.get("passes"), list) and len(plan["passes"]) == 236
        and isinstance(plan.get("requests"), list) and len(plan["requests"]) == LAST_ORDINAL,
        "Frozen baseline plan geometry differs",
    )
    requests = _request_index(plan)
    _require(requests[FIRST_SUFFIX_ORDINAL].get("batch_number") == 12, "Ordinal 81 is not pass-four batch 12")
    return plan, raw


def _request_index(plan: Mapping[str, Any]) -> dict[int, dict[str, Any]]:
    rows = plan.get("requests")
    _require(isinstance(rows, list), "Frozen request inventory differs")
    result = {row.get("ordinal"): dict(row) for row in rows if isinstance(row, Mapping) and type(row.get("ordinal")) is int}
    _require(set(result) == set(range(1, LAST_ORDINAL + 1)), "Frozen request ordinal inventory differs")
    return result


def _pass_index(plan: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    rows = plan.get("passes")
    _require(isinstance(rows, list), "Frozen pass inventory differs")
    result = {row.get("pass_id"): dict(row) for row in rows if isinstance(row, Mapping) and isinstance(row.get("pass_id"), str)}
    _require(len(result) == 236, "Frozen pass inventory differs")
    return result


def _source_for_pass(plan_root: Path, record: Mapping[str, Any]) -> dict[str, Any]:
    path = _relative(plan_root, record.get("input_path"), directory=False)
    raw = path.read_bytes()
    _require(_hash(raw) == record.get("source_sha256") and len(raw) == record.get("source_bytes"), "Frozen source payload differs")
    return {
        "opaque_story_id": record.get("logical_sample_id"),
        "source_opaque_story_id": record.get("opaque_story_id"),
        "story_text": raw.decode("utf-8"),
        "artifact_path": str(path),
        "sha256": _hash(raw),
    }


def _epoch_path(root: Path) -> Path:
    return root / "suffix-epoch.json"


def _attempt_path(root: Path, ordinal: int, name: str) -> Path:
    _require(FIRST_SUFFIX_ORDINAL <= ordinal <= LAST_ORDINAL, "Suffix ordinal differs")
    return root / "attempts" / f"request-{ordinal:04d}" / name


def _load_epoch(root: Path, expected: str) -> tuple[dict[str, Any], bytes]:
    raw = _read(_epoch_path(root), expected, "Suffix epoch")
    epoch = _json(raw, "Suffix epoch")
    required = {
        "schema_version", "evidence_class", "plan_sha256", "plan_root", "old_execution_root", "old_prefix_run_root",
        "old_prefix_manifest", "old_prefix_review", "old_execution_inventory_sha256", "old_execution_inventory",
        "old_prefix_run_inventory_sha256", "old_prefix_run_inventory",
        "recovered_study_manifest", "recovery_adoption_sha256", "recovery_amendment_sha256",
        "runtime_manifest", "runtime_package", "runtime_loader", "v3_source", "recovered_study_source",
        "old_runtime_manifest", "old_runtime_loader", "executor_source", "first_ordinal", "last_ordinal",
        "prefix_batches", "full_pass_batches", "dispatch_batch_size", "max_concurrency", "execution_mode",
        "provider_calls_made", "execution_authority",
    }
    _require(
        set(epoch) == required and epoch.get("schema_version") == 1
        and epoch.get("evidence_class") == "dryad_grok_v5_suffix_epoch_provider_free"
        and epoch.get("plan_sha256") == PLAN_SHA256
        and epoch.get("first_ordinal") == FIRST_SUFFIX_ORDINAL and epoch.get("last_ordinal") == LAST_ORDINAL
        and epoch.get("prefix_batches") == PREFIX_BATCHES and epoch.get("full_pass_batches") == FULL_PASS_BATCHES
        and epoch.get("dispatch_batch_size") == DISPATCH_BATCH_SIZE
        and epoch.get("max_concurrency") == MAX_WAVE_SIZE and epoch.get("execution_mode") == WAVE_EXECUTION_MODE
        and epoch.get("provider_calls_made") == 0 and epoch.get("execution_authority") is False,
        "Suffix epoch schema differs",
    )
    return epoch, raw


def _descriptor(path: Path, expected: str, label: str) -> dict[str, Any]:
    raw = _read(path, expected, label)
    return {"path": str(path), "sha256": expected, "bytes": len(raw)}


def _source_descriptor(path: Path, expected: str, label: str) -> dict[str, Any]:
    _read(path, expected, label)
    return {"path": str(path), "sha256": expected}


def _old_prefix(
    *,
    old_execution_root: Path,
    old_prefix_run_root: Path,
    manifest_path: Path,
    expected_manifest_sha256: str,
    review_path: Path,
    expected_review_sha256: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Validate the frozen eighty-contact record without granting it new authority."""
    manifest = _json(_read(manifest_path, expected_manifest_sha256, "Old prefix manifest"), "Old prefix manifest")
    review = _json(_read(review_path, expected_review_sha256, "Old prefix review"), "Old prefix review")
    anchors, counts, limits = manifest.get("anchors"), manifest.get("counts"), manifest.get("evidence_limits")
    _require(
        manifest.get("schema_version") == 1
        and manifest.get("decision") == "GO_actual_prefix_through80"
        and manifest.get("evidence_class") == "independent_actual_cohort8_settlement_and_mixed_prefix_replay"
        and isinstance(anchors, Mapping) and anchors.get("plan_sha256") == PLAN_SHA256
        and isinstance(counts, Mapping)
        and counts.get("logical_contacts") == 80 and counts.get("native_contacts") == 79
        and counts.get("study_recovered_contacts") == 1 and counts.get("study_recovered_ordinals") == [70]
        and counts.get("new_native_contacts") == 10 and counts.get("remaining_logical_requests") == 5348
        and manifest.get("native_identity_commitment_fields") == ["request_id_hash", "session_id_hash", "observed_turns"]
        and manifest.get("native_identity_commitment_sha256") == OLD_PREFIX_NATIVE_IDENTITY_COMMITMENT_SHA256
        and manifest.get("unique_native_request_ids") == 79 and manifest.get("unique_native_session_ids") == 79
        and isinstance(limits, Mapping) and limits.get("request81_present") is False
        and limits.get("execution_or_resend_authority") is False and limits.get("native_or_source_or_route_writes") == 0,
        "Old prefix manifest semantics differ",
    )
    records = manifest.get("per_pass")
    _require(isinstance(records, list) and len(records) == 4, "Old prefix pass inventory differs")
    partial = [item for item in records if isinstance(item, Mapping) and item.get("checkpoint_count") == PREFIX_BATCHES]
    _require(len(partial) == 1, "Old prefix partial pass differs")
    record = partial[0]
    _require(
        record.get("run_root") == str(old_prefix_run_root)
        and record.get("accepted_verdicts") == 88 and record.get("native_records") == 10
        and record.get("study_recovered_records") == 1,
        "Old prefix partial pass binding differs",
    )
    arguments = review.get("root_run_cohort8_arguments")
    _require(
        review.get("schema_version") == 1 and review.get("decision") == "GO_cohort8_71_through80"
        and review.get("evidence_class") == "independent_actual_dryad_cohort8_review"
        and review.get("provider_calls") == 0 and review.get("requests71_through80_absent") is True
        and review.get("resend70_authority") is False
        and isinstance(arguments, Mapping) and arguments.get("execution_root") == str(old_execution_root)
        and arguments.get("expected_plan_sha256") == PLAN_SHA256,
        "Old prefix review semantics differ",
    )
    return manifest, review


def _runtime_loader(path: Path, expected: str) -> ModuleType:
    return _load_module(path, expected, "_dryad_v5_runtime_")


def _runtime_from_epoch(epoch: Mapping[str, Any]) -> Any:
    loader = epoch.get("runtime_loader")
    manifest = epoch.get("runtime_manifest")
    package = epoch.get("runtime_package")
    _require(
        isinstance(loader, Mapping) and isinstance(manifest, Mapping) and isinstance(package, Mapping),
        "Suffix runtime binding differs",
    )
    module = _runtime_loader(_plain(loader.get("path"), directory=False), _sha(loader.get("sha256"), "Runtime loader"))
    value = module.load_runtime(
        _plain(manifest.get("path"), directory=False),
        expected_manifest_sha256=_sha(manifest.get("sha256"), "Runtime manifest"),
        runtime_package_root=_plain(package.get("root"), directory=True),
        expected_package_manifest_sha256=_sha(package.get("manifest_sha256"), "Runtime package manifest"),
    )
    _require(
        all(hasattr(value, name) for name in ("core", "runner", "broker", "adapter", "transport", "transport_sha256", "questions", "verify"))
        and value.transport_sha256 == epoch["v3_source"]["sha256"],
        "Suffix runtime namespace differs",
    )
    value.verify()
    return value


def _old_runtime_from_epoch(epoch: Mapping[str, Any]) -> Any:
    loader = epoch.get("old_runtime_loader")
    manifest = epoch.get("old_runtime_manifest")
    _require(isinstance(loader, Mapping) and isinstance(manifest, Mapping), "Old runtime binding differs")
    module = _runtime_loader(_plain(loader.get("path"), directory=False), _sha(loader.get("sha256"), "Old runtime loader"))
    value = module.load_runtime(
        _plain(manifest.get("path"), directory=False),
        expected_manifest_sha256=_sha(manifest.get("sha256"), "Old runtime manifest"),
    )
    _require(all(hasattr(value, name) for name in ("core", "runner", "broker", "adapter", "questions", "verify")), "Old runtime namespace differs")
    value.verify()
    return value


def prepare_suffix_epoch(
    *,
    plan_root: Path | str,
    old_execution_root: Path | str,
    old_prefix_run_root: Path | str,
    suffix_root: Path | str,
    old_prefix_manifest_path: Path | str,
    old_prefix_review_path: Path | str,
    runtime_manifest_path: Path | str,
    runtime_package_root: Path | str,
    runtime_loader_path: Path | str,
    old_runtime_manifest_path: Path | str,
    old_runtime_loader_path: Path | str,
    expected_plan_sha256: str,
    expected_old_prefix_manifest_sha256: str,
    expected_old_prefix_review_sha256: str,
    recovered_study_manifest_path: Path | str,
    expected_recovered_study_manifest_sha256: str,
    expected_recovery_adoption_sha256: str,
    expected_recovery_amendment_sha256: str,
    expected_runtime_manifest_sha256: str,
    expected_runtime_package_manifest_sha256: str,
    expected_runtime_loader_sha256: str,
    expected_old_runtime_manifest_sha256: str,
    expected_old_runtime_loader_sha256: str,
    expected_v3_sha256: str,
    expected_recovered_study_sha256: str,
    expected_executor_sha256: str,
    max_concurrency: int = MAX_WAVE_SIZE,
    execution_mode: str = WAVE_EXECUTION_MODE,
) -> dict[str, Any]:
    """Write one provider-free descendant epoch; this never creates a broker."""
    _require(expected_plan_sha256 == PLAN_SHA256, "Frozen baseline plan anchor differs")
    _require(type(max_concurrency) is int and max_concurrency == MAX_WAVE_SIZE, "Suffix wave concurrency differs")
    _require(execution_mode == WAVE_EXECUTION_MODE, "Suffix execution mode differs")
    plan_root = _plain(plan_root, directory=True)
    old_execution_root = _plain(old_execution_root, directory=True)
    old_prefix_run_root = _plain(old_prefix_run_root, directory=True)
    suffix_root = _plain(suffix_root, directory=True)
    manifest_path = _plain(old_prefix_manifest_path, directory=False)
    review_path = _plain(old_prefix_review_path, directory=False)
    recovered_study_manifest_path = _plain(recovered_study_manifest_path, directory=False)
    runtime_manifest_path = _plain(runtime_manifest_path, directory=False)
    package_root = _plain(runtime_package_root, directory=True)
    runtime_loader_path = _plain(runtime_loader_path, directory=False)
    old_runtime_manifest_path = _plain(old_runtime_manifest_path, directory=False)
    old_runtime_loader_path = _plain(old_runtime_loader_path, directory=False)
    _disjoint(plan_root, old_execution_root, old_prefix_run_root, suffix_root, package_root)
    _require(not _epoch_path(suffix_root).exists() and not any(suffix_root.iterdir()), "Suffix root must be empty")
    _plan(plan_root, expected_plan_sha256)
    _old_prefix(
        old_execution_root=old_execution_root,
        old_prefix_run_root=old_prefix_run_root,
        manifest_path=manifest_path,
        expected_manifest_sha256=expected_old_prefix_manifest_sha256,
        review_path=review_path,
        expected_review_sha256=expected_old_prefix_review_sha256,
    )
    _require(
        _json(manifest_path.read_bytes(), "Old prefix manifest")["anchors"].get("study70_manifest_sha256") == expected_recovered_study_manifest_sha256,
        "Old prefix does not bind the recovered study manifest",
    )
    own = _plain(Path(__file__), directory=False)
    _require(_hash(own.read_bytes()) == _sha(expected_executor_sha256, "Suffix executor"), "Suffix executor source differs")
    v3_path = _plain(REPOSITORY / "src/hbqrs/grok_broker_transport_v3.py", directory=False)
    _require(_hash(v3_path.read_bytes()) == _sha(expected_v3_sha256, "v3 transport"), "v3 transport source differs")
    recovered_path = _plain(ROOT / "baseline_recovered_study.py", directory=False)
    _require(_hash(recovered_path.read_bytes()) == _sha(expected_recovered_study_sha256, "Recovered study"), "Recovered study source differs")
    _read(runtime_manifest_path, expected_runtime_manifest_sha256, "Runtime manifest")
    _read(package_root / "candidate-manifest.json", expected_runtime_package_manifest_sha256, "Runtime package manifest")
    _read(runtime_loader_path, expected_runtime_loader_sha256, "Runtime loader")
    _read(old_runtime_manifest_path, expected_old_runtime_manifest_sha256, "Old runtime manifest")
    _read(old_runtime_loader_path, expected_old_runtime_loader_sha256, "Old runtime loader")
    old_inventory, prefix_inventory = _inventory(old_execution_root), _inventory(old_prefix_run_root)
    epoch = {
        "schema_version": 1,
        "evidence_class": "dryad_grok_v5_suffix_epoch_provider_free",
        "plan_sha256": expected_plan_sha256,
        "plan_root": str(plan_root),
        "old_execution_root": str(old_execution_root),
        "old_prefix_run_root": str(old_prefix_run_root),
        "old_prefix_manifest": _descriptor(manifest_path, expected_old_prefix_manifest_sha256, "Old prefix manifest"),
        "old_prefix_review": _descriptor(review_path, expected_old_prefix_review_sha256, "Old prefix review"),
        "old_execution_inventory_sha256": _hash(_canonical(old_inventory)),
        "old_execution_inventory": old_inventory,
        "old_prefix_run_inventory_sha256": _hash(_canonical(prefix_inventory)),
        "old_prefix_run_inventory": prefix_inventory,
        "recovered_study_manifest": _descriptor(recovered_study_manifest_path, expected_recovered_study_manifest_sha256, "Recovered study manifest"),
        "recovery_adoption_sha256": _sha(expected_recovery_adoption_sha256, "Recovery adoption"),
        "recovery_amendment_sha256": _sha(expected_recovery_amendment_sha256, "Recovery amendment"),
        "runtime_manifest": _source_descriptor(runtime_manifest_path, expected_runtime_manifest_sha256, "Runtime manifest"),
        "runtime_package": {"root": str(package_root), "manifest_sha256": expected_runtime_package_manifest_sha256},
        "runtime_loader": _source_descriptor(runtime_loader_path, expected_runtime_loader_sha256, "Runtime loader"),
        "v3_source": _source_descriptor(v3_path, expected_v3_sha256, "v3 transport"),
        "recovered_study_source": _source_descriptor(recovered_path, expected_recovered_study_sha256, "Recovered study"),
        "old_runtime_manifest": _source_descriptor(old_runtime_manifest_path, expected_old_runtime_manifest_sha256, "Old runtime manifest"),
        "old_runtime_loader": _source_descriptor(old_runtime_loader_path, expected_old_runtime_loader_sha256, "Old runtime loader"),
        "executor_source": _source_descriptor(own, expected_executor_sha256, "Suffix executor"),
        "first_ordinal": FIRST_SUFFIX_ORDINAL,
        "last_ordinal": LAST_ORDINAL,
        "prefix_batches": PREFIX_BATCHES,
        "full_pass_batches": FULL_PASS_BATCHES,
        "dispatch_batch_size": DISPATCH_BATCH_SIZE,
        "max_concurrency": max_concurrency,
        "execution_mode": execution_mode,
        "provider_calls_made": 0,
        "execution_authority": False,
    }
    _write_new(_epoch_path(suffix_root), _canonical(epoch))
    _require(_inventory(old_execution_root) == old_inventory and _inventory(old_prefix_run_root) == prefix_inventory, "Old evidence changed during preparation")
    return {"epoch_sha256": _hash(_epoch_path(suffix_root).read_bytes()), "provider_calls_made": 0, "execution_authority": False}


def _epoch_integrity(root: Path, epoch: Mapping[str, Any]) -> tuple[Path, Path, Path, dict[str, Any]]:
    """Recheck every immutable predecessor binding before a write or contact."""
    plan_root = _plain(epoch.get("plan_root"), directory=True)
    old_root = _plain(epoch.get("old_execution_root"), directory=True)
    prefix_root = _plain(epoch.get("old_prefix_run_root"), directory=True)
    package = epoch.get("runtime_package")
    _require(isinstance(package, Mapping), "Suffix runtime package binding differs")
    _disjoint(plan_root, old_root, prefix_root, root, _plain(package.get("root"), directory=True))
    _plan(plan_root, epoch["plan_sha256"])
    _old_prefix(
        old_execution_root=old_root,
        old_prefix_run_root=prefix_root,
        manifest_path=_plain(epoch["old_prefix_manifest"]["path"], directory=False),
        expected_manifest_sha256=epoch["old_prefix_manifest"]["sha256"],
        review_path=_plain(epoch["old_prefix_review"]["path"], directory=False),
        expected_review_sha256=epoch["old_prefix_review"]["sha256"],
    )
    recovered = epoch["recovered_study_manifest"]
    _require(isinstance(recovered, Mapping), "Recovered study binding differs")
    _read(_plain(recovered.get("path"), directory=False), recovered.get("sha256"), "Recovered study manifest")
    _require(
        _inventory(old_root) == epoch["old_execution_inventory"]
        and _hash(_canonical(epoch["old_execution_inventory"])) == epoch["old_execution_inventory_sha256"]
        and _inventory(prefix_root) == epoch["old_prefix_run_inventory"]
        and _hash(_canonical(epoch["old_prefix_run_inventory"])) == epoch["old_prefix_run_inventory_sha256"],
        "Old prefix evidence changed",
    )
    for name in ("runtime_manifest", "runtime_loader", "v3_source", "recovered_study_source", "old_runtime_manifest", "old_runtime_loader", "executor_source"):
        record = epoch[name]
        _require(isinstance(record, Mapping), "Suffix epoch source binding differs")
        _read(_plain(record.get("path"), directory=False), record.get("sha256"), "Suffix epoch source")
    _read(_plain(package.get("root"), directory=True) / "candidate-manifest.json", package.get("manifest_sha256"), "Runtime package manifest")
    return plan_root, old_root, prefix_root, _request_index(_plan(plan_root, epoch["plan_sha256"])[0])


def _review(
    path: Path,
    expected: str,
    *,
    epoch_sha256: str,
    epoch: Mapping[str, Any],
    live: bool,
) -> dict[str, Any]:
    raw = _read(path, expected, "Suffix independent review")
    value = _json(raw, "Suffix independent review")
    required = {
        "schema_version", "decision", "epoch_sha256", "plan_sha256", "executor_sha256", "runtime_manifest_sha256",
        "runtime_package_manifest_sha256", "v3_sha256", "old_prefix_manifest_sha256", "old_prefix_review_sha256",
        "candidate_package_root", "old_execution_inventory_sha256", "old_prefix_run_inventory_sha256", "suffix_ordinals",
        "execution_mode",
        "route", "route_sha256", "gate", "gate_sha256", "reviewed_at", "expires_at",
    }
    _require(
        set(value) == required and value.get("schema_version") == 1
        and value.get("decision") == "approved_dryad_grok_v5_suffix_epoch"
        and value.get("epoch_sha256") == epoch_sha256 and value.get("plan_sha256") == PLAN_SHA256
        and value.get("executor_sha256") == epoch["executor_source"]["sha256"]
        and value.get("runtime_manifest_sha256") == epoch["runtime_manifest"]["sha256"]
        and value.get("runtime_package_manifest_sha256") == epoch["runtime_package"]["manifest_sha256"]
        and value.get("v3_sha256") == epoch["v3_source"]["sha256"]
        and value.get("old_prefix_manifest_sha256") == epoch["old_prefix_manifest"]["sha256"]
        and value.get("old_prefix_review_sha256") == epoch["old_prefix_review"]["sha256"]
        and value.get("candidate_package_root") == epoch["runtime_package"]["root"]
        and value.get("old_execution_inventory_sha256") == epoch["old_execution_inventory_sha256"]
        and value.get("old_prefix_run_inventory_sha256") == epoch["old_prefix_run_inventory_sha256"]
        and value.get("suffix_ordinals") == [FIRST_SUFFIX_ORDINAL, LAST_ORDINAL]
        and value.get("execution_mode") == epoch["execution_mode"]
        and isinstance(value.get("route"), Mapping) and isinstance(value.get("gate"), Mapping)
        and value.get("route_sha256") == _hash(_canonical(dict(value["route"])))
        and value.get("gate_sha256") == _hash(_canonical(dict(value["gate"]))),
        "Suffix independent review binding differs",
    )
    route = value["route"]
    _require(
        type(route.get("timeout_seconds")) is int and route["timeout_seconds"] == REVIEW_TIMEOUT_SECONDS
        and type(route.get("max_concurrency")) is int and route["max_concurrency"] == epoch["max_concurrency"]
        and type(route.get("nonvisual_max_turns")) is int and route["nonvisual_max_turns"] == 1
        and route.get("provider") == "xai_grok_build" and route.get("adapter") == "grok_exec"
        and route.get("model") == "grok-4.6" and route.get("reasoning_effort") == "high"
        and isinstance(route.get("capabilities"), list) and "grok_nonvisual_history_v5" in route["capabilities"]
        and route.get("nonvisual_transport_contract") == "grok_nonvisual_history_v5"
        and isinstance(route.get("name"), str) and route["name"],
        "Suffix review route must remain 300/10/1 v5 Grok wave mode",
    )
    reviewed, expires = _time(value["reviewed_at"], "Review time"), _time(value["expires_at"], "Review expiry")
    if live:
        now = datetime.now(timezone.utc)
        _require(reviewed <= now < expires and expires - now >= timedelta(seconds=REVIEW_TIMEOUT_SECONDS), "Suffix review is not fresh for 300 seconds")
    return value


def _attempts(root: Path, epoch_sha256: str) -> dict[int, tuple[dict[str, Any], dict[str, Any] | None]]:
    attempts_root = root / "attempts"
    if not attempts_root.exists():
        return {}
    _require(attempts_root.is_dir() and not attempts_root.is_symlink(), "Suffix attempts root differs")
    result: dict[int, tuple[dict[str, Any], dict[str, Any] | None]] = {}
    for cell in attempts_root.iterdir():
        match = re.fullmatch(r"request-(\d{4})", cell.name)
        _require(match is not None and cell.is_dir() and not cell.is_symlink(), "Suffix attempt directory differs")
        ordinal = int(match.group(1))
        _require(FIRST_SUFFIX_ORDINAL <= ordinal <= LAST_ORDINAL and ordinal not in result, "Suffix attempt ordinal differs")
        allowed = {path.name for path in cell.iterdir()}
        _require(allowed <= {"attempt-start.json", "terminal.json", "contact-admission.json"} and "attempt-start.json" in allowed, "Suffix attempt file inventory differs")
        start = _json((cell / "attempt-start.json").read_bytes(), "Suffix attempt start")
        _require(start.get("ordinal") == ordinal and start.get("epoch_sha256") == epoch_sha256, "Suffix attempt start binding differs")
        terminal = _json((cell / "terminal.json").read_bytes(), "Suffix terminal") if "terminal.json" in allowed else None
        if terminal is not None:
            _require(
                terminal.get("ordinal") == ordinal and terminal.get("epoch_sha256") == epoch_sha256
                and terminal.get("attempt_start_sha256") == _hash((cell / "attempt-start.json").read_bytes())
                and terminal.get("status") in {"completed", "ambiguous"},
                "Suffix terminal binding differs",
            )
        result[ordinal] = (start, terminal)
    return result


def _next_ordinal(root: Path, epoch_sha256: str) -> int:
    records = _attempts(root, epoch_sha256)
    for ordinal in range(FIRST_SUFFIX_ORDINAL, LAST_ORDINAL + 1):
        pair = records.get(ordinal)
        if pair is None:
            _require(
                all(records[number][1] is not None and records[number][1].get("status") == "completed"
                    for number in range(FIRST_SUFFIX_ORDINAL, ordinal))
                and not any(number > ordinal for number in records),
                "A suffix attempt requires reconciliation",
            )
            for prior in range(FIRST_SUFFIX_ORDINAL, ordinal):
                _require_wave_settlement(root, epoch_sha256=epoch_sha256, ordinal=prior)
            return ordinal
        _require(pair[1] is not None and pair[1].get("status") == "completed",
                 "A suffix attempt is ambiguous or has no terminal status; reconcile before another request")
        _require_wave_settlement(root, epoch_sha256=epoch_sha256, ordinal=ordinal)
    raise ValueError("Frozen suffix has no remaining ordinal")


def _request_payload(plan_root: Path, row: Mapping[str, Any]) -> tuple[str, Path, list[str]]:
    prompt_path = _relative(plan_root, row.get("prompt_path"), directory=False)
    schema_path = _relative(plan_root, row.get("schema_path"), directory=False)
    prompt = prompt_path.read_bytes()
    schema = schema_path.read_bytes()
    question_ids = row.get("question_ids")
    _require(
        _hash(prompt) == row.get("prompt_sha256") and len(prompt) == row.get("prompt_bytes")
        and _hash(schema) == row.get("schema_sha256") and len(schema) == row.get("schema_bytes")
        and isinstance(question_ids, list) and 1 <= len(question_ids) <= DISPATCH_BATCH_SIZE
        and all(isinstance(item, str) and item for item in question_ids),
        "Frozen v5 request payload differs",
    )
    return prompt.decode("utf-8"), schema_path, list(question_ids)


def _run_root(root: Path, pass_id: str) -> Path:
    safe = Path(pass_id)
    _require(not safe.is_absolute() and all(part not in {"", ".", ".."} for part in safe.parts), "Suffix pass path differs")
    path = root / "passes" / safe
    _require(path.is_relative_to(root), "Suffix pass path escapes root")
    return path


def _attempt_run_root(root: Path, pass_id: str, ordinal: int) -> Path:
    path = _run_root(root, pass_id) / "requests" / f"request-{ordinal:04d}"
    _require(path.is_relative_to(root), "Suffix attempt output path escapes root")
    return path


def _context(
    *,
    runtime: Any,
    epoch_sha256: str,
    root: Path,
    row: Mapping[str, Any],
    prompt: str,
    schema_path: Path,
    question_ids: Sequence[str],
) -> dict[str, Any]:
    pass_id = row.get("pass_id")
    _require(isinstance(pass_id, str), "Suffix request pass differs")
    destination = _attempt_run_root(root, pass_id, row["ordinal"])
    config_sha256 = _hash(_canonical({"epoch_sha256": epoch_sha256, "pass_id": pass_id, "v3_sha256": runtime.transport_sha256}))
    value = runtime.runner._before_provider_attempt_context(
        destination=destination,
        schema_path=schema_path,
        run_id="dryad-grok-v5-suffix/" + pass_id,
        config_sha256=config_sha256,
        provider="grok",
        model="grok-4.6",
        reasoning="high",
        endpoint=None,
        batch_number=row["batch_number"],
        question_ids=question_ids,
        attempt_number=1,
        batch_attempts=1,
        base_prompt_sha256=_hash(prompt.encode("utf-8")),
        effective_prompt=prompt,
        feedback_policy=runtime.runner.VALIDATION_FEEDBACK_POLICY,
        feedback=None,
        rejected_chain={},
    )
    value["transport"] = {
        "protocol": "injected_grok_attempt_v1",
        "declared_sha256": runtime.transport_sha256,
        "identity_evidence": "caller_declared_unverified",
        "timeout": REVIEW_TIMEOUT_SECONDS,
        "allow_unattested_reasoning": True,
    }
    return value


def _terminal_evidence(root: Path, run_root: Path) -> dict[str, str]:
    if not run_root.exists():
        return {}
    _require(run_root.is_relative_to(root) and run_root.is_dir(), "Suffix provider evidence root differs")
    return _inventory(run_root)


def _terminal(
    *,
    root: Path,
    ordinal: int,
    epoch_sha256: str,
    start_path: Path,
    status: str,
    run_root: Path,
    contact_admitted: bool,
    context: Mapping[str, Any],
    content: str | None = None,
    metadata: Mapping[str, Any] | None = None,
    verdicts: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    _require(status in {"completed", "ambiguous"}, "Suffix terminal status differs")
    result: dict[str, Any] = {
        "format_version": 1,
        "ordinal": ordinal,
        "epoch_sha256": epoch_sha256,
        "attempt_start_sha256": _hash(start_path.read_bytes()),
        "status": status,
        "contact_admitted": contact_admitted,
        "context_sha256": _hash(_canonical(dict(context))),
        "provider_evidence_inventory": _terminal_evidence(root, run_root),
    }
    if content is not None:
        result["raw_response"] = content
        result["raw_response_sha256"] = _hash(content.encode("utf-8"))
    if metadata is not None:
        result["provider_metadata"] = dict(metadata)
        result["provider_metadata_sha256"] = _hash(_canonical(dict(metadata)))
    if verdicts is not None:
        result["verdicts"] = [dict(item) for item in verdicts]
        result["verdicts_sha256"] = _hash(_canonical(result["verdicts"]))
    _write_new(_attempt_path(root, ordinal, "terminal.json"), _canonical(result))
    return result


def _broker(runtime: Any, queue_root: Path, broker_factory: Any | None) -> Any:
    constructor = getattr(runtime.broker, "Broker", None)
    _require(isinstance(constructor, type), "Suffix runtime broker class differs")
    if broker_factory is None:
        broker = constructor(queue_root)
    else:
        _require(callable(broker_factory), "Suffix broker factory differs")
        broker = broker_factory(queue_root, constructor)
    _require(type(broker) is constructor and Path(broker.root).resolve() == queue_root.resolve(), "Suffix broker instance differs")
    return broker


def _wave_path(root: Path, start_ordinal: int, wave_size: int, suffix: str) -> Path:
    _require(type(start_ordinal) is int and type(wave_size) is int and 1 <= wave_size <= MAX_WAVE_SIZE,
             "Suffix wave geometry differs")
    last_ordinal = start_ordinal + wave_size - 1
    _require(FIRST_SUFFIX_ORDINAL <= start_ordinal <= last_ordinal <= LAST_ORDINAL, "Suffix wave ordinal differs")
    return root / "waves" / f"wave-{start_ordinal:04d}-{last_ordinal:04d}-{suffix}.json"


def _prepare_wave_cell(
    *, root: Path, epoch_sha256: str, epoch: Mapping[str, Any], plan_root: Path, requests: Mapping[int, Any],
    review_path: Path, review_sha256: str, review: Mapping[str, Any], ordinal: int, wave_size: int, slot_index: int,
) -> dict[str, Any]:
    runtime = _runtime_from_epoch(epoch)
    row = dict(requests[ordinal])
    plan, _ = _plan(plan_root, epoch["plan_sha256"])
    passed = _pass_index(plan).get(row.get("pass_id"))
    _require(isinstance(passed, Mapping) and row.get("logical_sample_id") == passed.get("logical_sample_id"),
             "Suffix request/pass binding differs")
    pass_rows, mixed_prefix = _pass_requests(plan, row["pass_id"])
    _require(row in pass_rows and row.get("batch_number") >= (12 if mixed_prefix else 1), "Suffix request/pass boundary differs")
    prompt, schema_path, question_ids = _request_payload(plan_root, row)
    source = _source_for_pass(plan_root, passed)
    context = _context(runtime=runtime, epoch_sha256=epoch_sha256, root=root, row=row, prompt=prompt,
                       schema_path=schema_path, question_ids=question_ids)
    start = {
        "format_version": 1, "ordinal": ordinal, "epoch_sha256": epoch_sha256, "plan_sha256": epoch["plan_sha256"],
        "pass_id": row["pass_id"], "batch_number": row["batch_number"], "question_ids": question_ids,
        "prompt_sha256": row["prompt_sha256"], "schema_sha256": row["schema_sha256"],
        "review": {"path": str(review_path), "sha256": review_sha256},
        "route_sha256": review["route_sha256"], "gate_sha256": review["gate_sha256"],
        "runtime_manifest_sha256": epoch["runtime_manifest"]["sha256"],
        "runtime_package_manifest_sha256": epoch["runtime_package"]["manifest_sha256"],
        "v3_sha256": epoch["v3_source"]["sha256"], "executor_sha256": epoch["executor_source"]["sha256"],
        "wave": {"start_ordinal": ordinal - slot_index, "wave_size": wave_size, "slot_index": slot_index},
        "context": context, "context_sha256": _hash(_canonical(context)),
        "run_root": str(_attempt_run_root(root, row["pass_id"], ordinal)),
    }
    return {"runtime": runtime, "row": row, "passed": dict(passed), "prompt": prompt, "schema_path": schema_path,
            "question_ids": question_ids, "source": source, "context": context, "start": start,
            "start_path": _attempt_path(root, ordinal, "attempt-start.json"),
            "run_root": _attempt_run_root(root, row["pass_id"], ordinal)}


def _contact_prepared_cell(
    *, prepared: Mapping[str, Any], root: Path, epoch_sha256: str, epoch: Mapping[str, Any], epoch_raw: bytes,
    plan_root: Path, old_root: Path, prefix_root: Path, requests: Mapping[int, Any], review_path: Path,
    review_sha256: str, review: Mapping[str, Any], queue_root: Path, broker_factory: Any | None,
    stop_event: threading.Event,
) -> dict[str, Any]:
    runtime, row, passed = prepared["runtime"], prepared["row"], prepared["passed"]
    ordinal, start, start_path = row["ordinal"], prepared["start"], prepared["start_path"]
    context, source, run_root = prepared["context"], prepared["source"], prepared["run_root"]
    content: str | None = None
    metadata: Mapping[str, Any] | None = None
    admitted = False
    try:
        _require(not stop_event.is_set(), "Wave stopped before native contact")
        broker = _broker(runtime, queue_root, broker_factory)

        def before_contact(callback_context: Mapping[str, Any]) -> None:
            nonlocal admitted
            _require(not stop_event.is_set(), "Wave stopped before native contact")
            _require(_epoch_path(root).read_bytes() == epoch_raw, "Suffix epoch changed before contact")
            current_epoch, _ = _load_epoch(root, epoch_sha256)
            current_plan, current_old, current_prefix, current_requests = _epoch_integrity(root, current_epoch)
            _require(
                current_plan == plan_root and current_old == old_root and current_prefix == prefix_root
                and current_requests[ordinal] == row and _hash(_canonical(dict(callback_context))) == start["context_sha256"],
                "Frozen suffix context changed before contact",
            )
            _review(review_path, review_sha256, epoch_sha256=epoch_sha256, epoch=current_epoch, live=True)
            runtime.verify()
            _require(_source_for_pass(plan_root, passed) == source, "Frozen suffix source changed before contact")
            _require(not stop_event.is_set(), "Wave stopped before native contact")
            _write_new(
                _attempt_path(root, ordinal, "contact-admission.json"),
                _canonical({"format_version": 1, "ordinal": ordinal, "epoch_sha256": epoch_sha256,
                            "attempt_start_sha256": _hash(start_path.read_bytes()), "context_sha256": start["context_sha256"],
                            "route_sha256": review["route_sha256"], "gate_sha256": review["gate_sha256"],
                            "admitted_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")} ),
            )
            admitted = True

        transport = runtime.transport.bind_grok_broker_transport(
            broker=broker, route=review["route"], before_contact=before_contact, runtime_check=runtime.verify,
        )
        content, metadata = transport(context)
        _require(isinstance(content, str) and isinstance(metadata, Mapping), "v3 transport result differs")
        runtime.runner._validate_grok_transport_evidence(run_root, metadata)
        normalized = runtime.runner._normalize_batch(
            runtime.runner._parse_model_json(content), expected_ids=prepared["question_ids"],
            artifact_id=source["opaque_story_id"], bundle_id="prose.short_story", judge_id="grok:grok-4.6",
            run_id=context["run"]["run_id"], artifact_text=source["story_text"], context_texts=[],
            normalization_policy=runtime.runner.EVIDENCE_NORMALIZATION_POLICY, repair_audit=[],
        )
        _require(admitted, "v3 transport returned before contact admission")
        runtime.verify()
        _epoch_integrity(root, epoch)
        terminal = _terminal(root=root, ordinal=ordinal, epoch_sha256=epoch_sha256, start_path=start_path, status="completed",
                             run_root=run_root, contact_admitted=True, context=context, content=content, metadata=metadata, verdicts=normalized)
        return {"ordinal": ordinal, "status": "completed_pending_replay",
                "terminal_sha256": _hash(_attempt_path(root, ordinal, "terminal.json").read_bytes()),
                "contact_admitted": terminal["contact_admitted"], "provider_calls_made": 1}
    except Exception:
        if not _attempt_path(root, ordinal, "terminal.json").exists():
            _terminal(root=root, ordinal=ordinal, epoch_sha256=epoch_sha256, start_path=start_path, status="ambiguous",
                      run_root=run_root, contact_admitted=admitted, context=context, content=content, metadata=metadata)
        raise


def _wave_settlement(root: Path, *, epoch_sha256: str, start_ordinal: int, wave_size: int, wave_start_sha256: str) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for ordinal in range(start_ordinal, start_ordinal + wave_size):
        terminal_path = _attempt_path(root, ordinal, "terminal.json")
        terminal = _json(terminal_path.read_bytes(), "Suffix terminal") if terminal_path.is_file() else None
        row: dict[str, Any] = {"ordinal": ordinal, "terminal_sha256": _hash(terminal_path.read_bytes()) if terminal else None,
                               "status": terminal.get("status") if terminal else "unsettled",
                               "contact_admitted": terminal.get("contact_admitted") if terminal else False}
        if terminal and terminal.get("status") == "completed":
            metadata = terminal.get("provider_metadata")
            _require(isinstance(metadata, Mapping), "Completed wave identity differs")
            row["native_identity"] = {"request_id_hash": metadata.get("request_id_sha256"),
                                      "session_id_hash": metadata.get("session_id_sha256")}
        rows.append(row)
    completed = [item["native_identity"] for item in rows if "native_identity" in item]
    request_ids = [item["request_id_hash"] for item in completed]
    session_ids = [item["session_id_hash"] for item in completed]
    _require(all(isinstance(value, str) and _HASH.fullmatch(value) for value in request_ids + session_ids)
             and len(request_ids) == len(set(request_ids)) and len(session_ids) == len(set(session_ids)),
             "Wave native identity collision")
    return {"format_version": 1, "epoch_sha256": epoch_sha256, "start_ordinal": start_ordinal,
            "wave_size": wave_size, "wave_start_sha256": wave_start_sha256, "rows": rows}


def dispatch_wave(
    *, suffix_root: Path | str, expected_epoch_sha256: str, start_ordinal: int, wave_size: int,
    reviewed_path: Path | str, expected_review_sha256: str, queue_root: Path | str, broker_factory: Any | None = None,
) -> dict[str, Any]:
    """Reserve, dispatch, and settle one contiguous, bounded Grok v5 wave."""
    root = _plain(suffix_root, directory=True)
    epoch_sha256 = _sha(expected_epoch_sha256, "Suffix epoch")
    epoch, epoch_raw = _load_epoch(root, epoch_sha256)
    _require(type(start_ordinal) is int and start_ordinal == _next_ordinal(root, epoch_sha256),
             "Suffix wave is not the exact next cell")
    _require(type(wave_size) is int and 1 <= wave_size <= epoch["max_concurrency"] and start_ordinal + wave_size - 1 <= LAST_ORDINAL,
             "Suffix wave size differs")
    review_path, queue_root = _plain(reviewed_path, directory=False), _plain(queue_root, directory=True)
    plan_root, old_root, prefix_root, requests = _epoch_integrity(root, epoch)
    _disjoint(root, queue_root, old_root, prefix_root, plan_root)
    review_sha256 = _sha(expected_review_sha256, "Suffix review")
    review = _review(review_path, review_sha256, epoch_sha256=epoch_sha256, epoch=epoch, live=True)
    starts = [_attempt_path(root, ordinal, "attempt-start.json") for ordinal in range(start_ordinal, start_ordinal + wave_size)]
    _require(not any(path.exists() for path in starts), "Suffix wave already has a reserved attempt")
    prepared = [_prepare_wave_cell(root=root, epoch_sha256=epoch_sha256, epoch=epoch, plan_root=plan_root, requests=requests,
                                   review_path=review_path, review_sha256=review_sha256, review=review, ordinal=ordinal,
                                   wave_size=wave_size, slot_index=ordinal - start_ordinal)
                for ordinal in range(start_ordinal, start_ordinal + wave_size)]
    for item in prepared:
        _write_new(item["start_path"], _canonical(item["start"]))
    wave_start = {"format_version": 1, "epoch_sha256": epoch_sha256, "epoch_source_sha256": _hash(epoch_raw),
                  "execution_mode": epoch["execution_mode"], "max_concurrency": epoch["max_concurrency"],
                  "start_ordinal": start_ordinal, "wave_size": wave_size,
                  "review": {"path": str(review_path), "sha256": review_sha256}, "route_sha256": review["route_sha256"],
                  "gate_sha256": review["gate_sha256"], "runtime_manifest_sha256": epoch["runtime_manifest"]["sha256"],
                  "runtime_package_manifest_sha256": epoch["runtime_package"]["manifest_sha256"],
                  "v3_sha256": epoch["v3_source"]["sha256"],
                  "rows": [{"ordinal": item["row"]["ordinal"], "slot_index": index,
                            "pass_id": item["row"]["pass_id"], "source_sha256": item["source"]["sha256"],
                            "context_sha256": item["start"]["context_sha256"], "attempt_start_sha256": _hash(_canonical(item["start"]))}
                           for index, item in enumerate(prepared)]}
    wave_start_path = _wave_path(root, start_ordinal, wave_size, "start")
    _write_new(wave_start_path, _canonical(wave_start))
    wave_start_sha256 = _hash(wave_start_path.read_bytes())
    stop_event, errors, results = threading.Event(), [], {}

    def run_cell(item: Mapping[str, Any], cell_queue: Path) -> dict[str, Any]:
        try:
            return _contact_prepared_cell(prepared=item, root=root, epoch_sha256=epoch_sha256, epoch=epoch,
                                          epoch_raw=epoch_raw, plan_root=plan_root, old_root=old_root,
                                          prefix_root=prefix_root, requests=requests, review_path=review_path,
                                          review_sha256=review_sha256, review=review, queue_root=cell_queue,
                                          broker_factory=broker_factory, stop_event=stop_event)
        except Exception:
            stop_event.set()
            raise

    with ThreadPoolExecutor(max_workers=wave_size, thread_name_prefix="dryad-grok-v5") as executor:
        futures: dict[Future[dict[str, Any]], int] = {}
        pending = iter(prepared)
        while True:
            while not stop_event.is_set() and len(futures) < wave_size:
                try:
                    item = next(pending)
                except StopIteration:
                    break
                future = executor.submit(run_cell, item, queue_root)
                futures[future] = item["row"]["ordinal"]
            if not futures:
                break
            done, _ = wait(tuple(futures), return_when=FIRST_COMPLETED)
            for future in done:
                ordinal = futures.pop(future)
                try:
                    results[ordinal] = future.result()
                except Exception as error:  # noqa: BLE001 - every worker failure must stop peers before re-raising.
                    stop_event.set()
                    errors.append(error)
    settlement = _wave_settlement(root, epoch_sha256=epoch_sha256, start_ordinal=start_ordinal, wave_size=wave_size,
                                  wave_start_sha256=wave_start_sha256)
    _write_new(_wave_path(root, start_ordinal, wave_size, "settlement"), _canonical(settlement))
    if errors:
        raise errors[0]
    return {"start_ordinal": start_ordinal, "wave_size": wave_size, "execution_mode": epoch["execution_mode"],
            "max_concurrency": epoch["max_concurrency"], "wave_start_sha256": wave_start_sha256,
            "settlement_sha256": _hash(_wave_path(root, start_ordinal, wave_size, "settlement").read_bytes()),
            "rows": [results[ordinal] for ordinal in range(start_ordinal, start_ordinal + wave_size)],
            "provider_calls_made": wave_size}


def dispatch_one(**kwargs: Any) -> dict[str, Any]:
    """Run the common wave executor as a one-cell canary wrapper."""
    ordinal = kwargs.pop("ordinal")
    result = dispatch_wave(start_ordinal=ordinal, wave_size=1, **kwargs)
    return result["rows"][0]


def _approved_route(routes: Mapping[str, Any], route_sha256: Any, label: str) -> dict[str, Any]:
    route_sha256 = _sha(route_sha256, label + " route")
    value = routes.get(route_sha256)
    _require(isinstance(value, Mapping) and _hash(_canonical(dict(value))) == route_sha256, f"{label} route binding differs")
    return dict(value)


def _pass_requests(plan: Mapping[str, Any], pass_id: str) -> tuple[list[dict[str, Any]], bool]:
    records = [dict(row) for row in _request_index(plan).values() if row.get("pass_id") == pass_id]
    records.sort(key=lambda row: row["batch_number"])
    ordinals = [row.get("ordinal") for row in records]
    _require(
        len(records) == FULL_PASS_BATCHES and [row.get("batch_number") for row in records] == list(range(1, FULL_PASS_BATCHES + 1)),
        "Suffix pass geometry differs",
    )
    mixed_prefix = ordinals == list(range(70, 93))
    _require(mixed_prefix or (type(ordinals[0]) is int and ordinals == list(range(ordinals[0], ordinals[0] + FULL_PASS_BATCHES))
                              and ordinals[0] >= FIRST_SUFFIX_ORDINAL), "Suffix pass ordinal geometry differs")
    return records, mixed_prefix


def _artifact_bytes(runtime: Any, run_root: Path, descriptor: Any, label: str) -> bytes:
    _require(
        isinstance(descriptor, Mapping) and set(descriptor) == {"path", "bytes", "sha256"}
        and isinstance(descriptor.get("path"), str) and type(descriptor.get("bytes")) is int and descriptor["bytes"] >= 0
        and isinstance(descriptor.get("sha256"), str) and _HASH.fullmatch(descriptor["sha256"]) is not None,
        f"v3 {label} artifact descriptor differs",
    )
    path = _relative(run_root, descriptor["path"], directory=False)
    raw = path.read_bytes()
    _require(
        len(raw) == descriptor["bytes"] and _hash(raw) == descriptor["sha256"]
        and runtime.runner._provider_artifact(run_root, path) == dict(descriptor),
        f"v3 {label} artifact bytes differ",
    )
    return raw


def _read_only_native_replay(runtime: Any, *, result: Mapping[str, Any], envelope_raw: bytes,
                             route: Mapping[str, Any], prompt: str, schema: Mapping[str, Any]) -> dict[str, str]:
    """Reparse one retained v3 envelope without constructing or contacting a broker."""
    native = _json(envelope_raw, "v3 native envelope")
    session = native.get("sessionId")
    _require(isinstance(session, str) and str(uuid.UUID(session)) == session, "v3 native session differs")
    output, identity, usage = runtime.adapter._parse_grok_envelope(
        envelope_raw, model="grok-4.6", reported_model="grok-4.6-build", session_id=session,
        schema=dict(schema), max_turns=1, exact_turns=True,
    )
    descriptor = result.get("native_envelope_artifact")
    _require(
        isinstance(descriptor, Mapping) and descriptor == {"schema_version": 1, "sha256": _hash(envelope_raw), "byte_length": len(envelope_raw)},
        "v3 native envelope descriptor differs",
    )

    def read_envelope(self: Any, requested: Any) -> bytes:
        _require(requested == descriptor, "v3 read-only envelope descriptor differs")
        return envelope_raw

    def forbidden(*_args: Any, **_kwargs: Any) -> None:
        raise AssertionError("Native replay attempted broker state access")

    base = runtime.broker.Broker
    _require(isinstance(base, type), "v5 runtime broker class differs")
    replay_class = type("DryadReadOnlyNativeReplay", (base,), {
        "read_grok_native_envelope": read_envelope,
        "_connect_grok_host_gate": forbidden,
        "_connect": forbidden,
        "init": forbidden,
        "_run_grok_exec": forbidden,
    })
    replay = object.__new__(replay_class)
    execution_route = {**dict(route), "output_schema": dict(schema), "nonvisual_max_turns": 1}
    checked = replay._parse_grok_exec_envelope(
        _canonical({"control": {"version": 1, "state": "completed"}, "result": dict(result)}),
        execution_route, {"prompt": prompt}, expected_session_id=session,
    )
    runtime_record = result.get("runtime")
    _require(
        getattr(checked, "state", None) == "completed" and getattr(checked, "result", None) == result
        and isinstance(runtime_record, Mapping) and output == result.get("output")
        and usage == runtime_record.get("usage_telemetry")
        and all(identity.get(key) == runtime_record.get(key) for key in identity),
        "v3 native envelope semantic replay differs",
    )
    return {"request_id_hash": identity["request_id_hash"], "session_id_hash": identity["session_id_hash"]}


def _replay_suffix_terminal(
    *,
    root: Path,
    epoch_sha256: str,
    epoch: Mapping[str, Any],
    runtime: Any,
    plan_root: Path,
    passed: Mapping[str, Any],
    row: Mapping[str, Any],
    approved_v5_routes: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    ordinal = row["ordinal"]
    start_path = _attempt_path(root, ordinal, "attempt-start.json")
    terminal_path = _attempt_path(root, ordinal, "terminal.json")
    _require(start_path.is_file() and terminal_path.is_file(), "Suffix batch is not terminal")
    start = _json(start_path.read_bytes(), "Suffix attempt start")
    terminal = _json(terminal_path.read_bytes(), "Suffix terminal")
    _require(
        terminal.get("status") == "completed" and terminal.get("contact_admitted") is True
        and start.get("ordinal") == ordinal and start.get("epoch_sha256") == epoch_sha256
        and terminal.get("attempt_start_sha256") == _hash(start_path.read_bytes())
        and start.get("pass_id") == row.get("pass_id") and start.get("batch_number") == row.get("batch_number")
        and start.get("question_ids") == row.get("question_ids") and start.get("prompt_sha256") == row.get("prompt_sha256")
        and start.get("schema_sha256") == row.get("schema_sha256"),
        "Suffix terminal start binding differs",
    )
    review_record = start.get("review")
    _require(isinstance(review_record, Mapping) and set(review_record) == {"path", "sha256"}, "Suffix terminal review binding differs")
    recorded_review = _review(
        _plain(review_record["path"], directory=False), _sha(review_record["sha256"], "Recorded suffix review"),
        epoch_sha256=epoch_sha256, epoch=epoch, live=False,
    )
    _require(
        recorded_review["route_sha256"] == start["route_sha256"] and recorded_review["gate_sha256"] == start["gate_sha256"],
        "Suffix terminal review route or gate differs",
    )
    _require(
        start.get("runtime_manifest_sha256") == epoch["runtime_manifest"]["sha256"]
        and start.get("runtime_package_manifest_sha256") == epoch["runtime_package"]["manifest_sha256"]
        and start.get("v3_sha256") == epoch["v3_source"]["sha256"]
        and start.get("executor_sha256") == epoch["executor_source"]["sha256"],
        "Suffix terminal epoch binding differs",
    )
    prompt, schema_path, question_ids = _request_payload(plan_root, row)
    expected_context = _context(
        runtime=runtime, epoch_sha256=epoch_sha256, root=root, row=row, prompt=prompt,
        schema_path=schema_path, question_ids=question_ids,
    )
    _require(
        start.get("context") == expected_context and start.get("context_sha256") == _hash(_canonical(expected_context))
        and terminal.get("context_sha256") == start["context_sha256"],
        "Suffix terminal callback context differs",
    )
    run_root = _attempt_run_root(root, row["pass_id"], ordinal)
    recorded_inventory = terminal.get("provider_evidence_inventory")
    current_inventory = _terminal_evidence(root, run_root)
    _require(
        start.get("run_root") == str(run_root) and isinstance(recorded_inventory, Mapping)
        and all(current_inventory.get(path) == value for path, value in recorded_inventory.items()),
        "Suffix terminal evidence inventory differs",
    )
    contact_path = _attempt_path(root, ordinal, "contact-admission.json")
    contact = _json(contact_path.read_bytes(), "Suffix contact admission")
    _require(
        set(contact) == {"format_version", "ordinal", "epoch_sha256", "attempt_start_sha256", "context_sha256", "route_sha256", "gate_sha256", "admitted_at"}
        and contact.get("format_version") == 1 and contact.get("ordinal") == ordinal and contact.get("epoch_sha256") == epoch_sha256
        and contact.get("attempt_start_sha256") == _hash(start_path.read_bytes()) and contact.get("context_sha256") == start["context_sha256"]
        and contact.get("route_sha256") == start["route_sha256"] and contact.get("gate_sha256") == start["gate_sha256"],
        "Suffix contact admission binding differs",
    )
    route = _approved_route(approved_v5_routes, start["route_sha256"], "v5")
    _require(
        route == recorded_review["route"] and route.get("provider") == "xai_grok_build" and route.get("adapter") == "grok_exec"
        and route.get("timeout_seconds") == REVIEW_TIMEOUT_SECONDS and route.get("max_concurrency") == epoch["max_concurrency"]
        and route.get("nonvisual_max_turns") == 1 and route.get("nonvisual_transport_contract") == "grok_nonvisual_history_v5"
        and isinstance(route.get("capabilities"), list) and "grok_nonvisual_history_v5" in route["capabilities"],
        "v5 approved route differs",
    )
    content, metadata = terminal.get("raw_response"), terminal.get("provider_metadata")
    _require(
        isinstance(content, str) and isinstance(metadata, Mapping)
        and terminal.get("raw_response_sha256") == _hash(content.encode("utf-8"))
        and terminal.get("provider_metadata_sha256") == _hash(_canonical(dict(metadata))),
        "Suffix terminal raw provider result differs",
    )
    _require(
        set(metadata) == {"model", "evidence_sha256", "request_id_sha256", "session_id_sha256", "reasoning_attested", "tool_free", "provider_artifacts"}
        and metadata.get("model") == route["model"] and metadata.get("reasoning_attested") is False and metadata.get("tool_free") is True
        and isinstance(metadata.get("provider_artifacts"), Mapping) and set(metadata["provider_artifacts"]) == {"request", "context", "outcome", "envelope", "receipt"},
        "v3 provider metadata differs",
    )
    runtime.runner._validate_grok_transport_evidence(run_root, metadata)
    artifacts = metadata["provider_artifacts"]
    request_raw = _artifact_bytes(runtime, run_root, artifacts["request"], "request")
    context_raw = _artifact_bytes(runtime, run_root, artifacts["context"], "context")
    outcome_raw = _artifact_bytes(runtime, run_root, artifacts["outcome"], "outcome")
    envelope_raw = _artifact_bytes(runtime, run_root, artifacts["envelope"], "envelope")
    receipt_raw = _artifact_bytes(runtime, run_root, artifacts["receipt"], "receipt")
    _require(metadata["evidence_sha256"] == _hash(receipt_raw), "v3 metadata receipt differs")
    _require(request_raw == _canonical({"prompt": prompt}), "v3 request bytes differ")
    _prompt, schema, _destination, _batch, _attempt, bindings = runtime.transport._context_bindings(expected_context, route)
    _require(_prompt == prompt and _destination == run_root and _batch == row["batch_number"] and _attempt == 1
             and context_raw == _canonical(bindings), "v3 context semantic reconstruction differs")
    outcome = _json(outcome_raw, "v3 outcome")
    _require(set(outcome) == {"state", "result", "failure"} and outcome.get("state") == "completed"
             and outcome.get("failure") is None and isinstance(outcome.get("result"), Mapping), "v3 outcome differs")
    result = dict(outcome["result"])
    runtime_record = result.get("runtime")
    execution = runtime_record.get("execution_contract") if isinstance(runtime_record, Mapping) else None
    v5_contract = getattr(runtime.transport, "_V5_NONVISUAL_TRANSPORT_CONTRACT", None)
    v5_contract_sha = getattr(runtime.transport, "_V5_TRANSPORT_CONTRACT_SHA256", None)
    _require(
        set(result) == {"schema_version", "request_hash", "output", "output_hash", "runtime", "native_envelope_artifact"}
        and result.get("schema_version") == 2 and result.get("request_hash") == _hash(request_raw)
        and result.get("output_hash") == _hash(_canonical(result.get("output")))
        and isinstance(runtime_record, Mapping) and runtime_record.get("adapter_version") == 5
        and runtime_record.get("requested_model") == route["model"] and runtime_record.get("requested_reasoning_effort") == route["reasoning_effort"]
        and runtime_record.get("identity_evidence") == "requested_only" and runtime_record.get("reasoning_attested") is False
        and runtime_record.get("execution_policy") == "bounded_nonvisual_deny_wins_attested"
        and runtime_record.get("nonvisual_max_turns") == 1 and runtime_record.get("observed_turns") == 1
        and isinstance(runtime_record.get("tool_policy_attestation_hash"), str) and _HASH.fullmatch(runtime_record["tool_policy_attestation_hash"])
        and isinstance(execution, Mapping) and execution == bindings["execution_contract"]
        and execution.get("tools") == "deny_wins_none_attested" and execution.get("max_turns") == 1
        and execution.get("nonvisual_transport_contract") == v5_contract and execution.get("nonvisual_transport_contract_sha256") == v5_contract_sha,
        "v3 v5 runtime contract differs",
    )
    _require(content == json.dumps(result["output"], ensure_ascii=False), "v3 raw response differs from outcome")
    identity = _read_only_native_replay(runtime, result=result, envelope_raw=envelope_raw, route=route, prompt=prompt, schema=schema)
    expected_receipt = {
        "schema_version": 1, "source_sha256": epoch["v3_source"]["sha256"], "route_sha256": start["route_sha256"],
        "request_sha256": _hash(request_raw), "context_sha256": _hash(context_raw),
        "schema_sha256": bindings["response_schema_sha256"], "result_sha256": _hash(_canonical(result)),
        "outcome_sha256": _hash(outcome_raw), "envelope_sha256": _hash(envelope_raw),
        "session_id_hash": identity["session_id_hash"], "request_id_hash": identity["request_id_hash"],
    }
    _require(receipt_raw == _canonical(expected_receipt) and metadata["request_id_sha256"] == identity["request_id_hash"]
             and metadata["session_id_sha256"] == identity["session_id_hash"], "v3 receipt semantic reconstruction differs")
    parsed = runtime.runner._parse_model_json(content)
    source = _source_for_pass(plan_root, passed)
    normalized = runtime.runner._normalize_batch(
        parsed,
        expected_ids=question_ids,
        artifact_id=source["opaque_story_id"],
        bundle_id="prose.short_story",
        judge_id="grok:grok-4.6",
        run_id=expected_context["run"]["run_id"],
        artifact_text=source["story_text"],
        context_texts=[],
        normalization_policy=runtime.runner.EVIDENCE_NORMALIZATION_POLICY,
        repair_audit=[],
    )
    _require(
        terminal.get("verdicts") == normalized and terminal.get("verdicts_sha256") == _hash(_canonical(normalized)),
        "Suffix terminal normalized verdicts differ",
    )
    return normalized, identity


def _completed_v5_identities(root: Path, epoch_sha256: str) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    for _start, terminal in _attempts(root, epoch_sha256).values():
        if terminal is None or terminal.get("status") != "completed":
            continue
        metadata = terminal.get("provider_metadata")
        _require(
            isinstance(metadata, Mapping) and terminal.get("provider_metadata_sha256") == _hash(_canonical(dict(metadata)))
            and isinstance(metadata.get("request_id_sha256"), str) and _HASH.fullmatch(metadata["request_id_sha256"])
            and isinstance(metadata.get("session_id_sha256"), str) and _HASH.fullmatch(metadata["session_id_sha256"]),
            "Completed v5 identity record differs",
        )
        result.append({"request_id_hash": metadata["request_id_sha256"], "session_id_hash": metadata["session_id_sha256"]})
    request_ids = [item["request_id_hash"] for item in result]
    session_ids = [item["session_id_hash"] for item in result]
    _require(len(request_ids) == len(set(request_ids)) and len(session_ids) == len(set(session_ids)), "Global v5 native identity collision")
    return result


def _wave_start(root: Path, *, epoch_sha256: str, start_ordinal: int, wave_size: int) -> tuple[dict[str, Any], bytes]:
    path = _wave_path(root, start_ordinal, wave_size, "start")
    raw = path.read_bytes()
    value = _json(raw, "Suffix wave start")
    required = {"format_version", "epoch_sha256", "epoch_source_sha256", "execution_mode", "max_concurrency",
                "start_ordinal", "wave_size", "review", "route_sha256", "gate_sha256", "runtime_manifest_sha256",
                "runtime_package_manifest_sha256", "v3_sha256", "rows"}
    _require(
        set(value) == required and value.get("format_version") == 1 and value.get("epoch_sha256") == epoch_sha256
        and value.get("start_ordinal") == start_ordinal and value.get("wave_size") == wave_size
        and value.get("execution_mode") == WAVE_EXECUTION_MODE and value.get("max_concurrency") == MAX_WAVE_SIZE
        and isinstance(value.get("rows"), list) and len(value["rows"]) == wave_size,
        "Suffix wave start binding differs",
    )
    slots = [item.get("slot_index") for item in value["rows"] if isinstance(item, Mapping)]
    ordinals = [item.get("ordinal") for item in value["rows"] if isinstance(item, Mapping)]
    _require(slots == list(range(wave_size)) and ordinals == list(range(start_ordinal, start_ordinal + wave_size)),
             "Suffix wave slot inventory differs")
    return value, raw


def _require_wave_settlement(root: Path, *, epoch_sha256: str, ordinal: int) -> None:
    start = _json(_attempt_path(root, ordinal, "attempt-start.json").read_bytes(), "Suffix attempt start")
    binding = start.get("wave")
    _require(isinstance(binding, Mapping) and set(binding) == {"start_ordinal", "wave_size", "slot_index"}
             and type(binding.get("start_ordinal")) is int and type(binding.get("wave_size")) is int
             and type(binding.get("slot_index")) is int and binding["start_ordinal"] + binding["slot_index"] == ordinal,
             "Suffix attempt wave ownership differs")
    wave, raw = _wave_start(root, epoch_sha256=epoch_sha256, start_ordinal=binding["start_ordinal"], wave_size=binding["wave_size"])
    row = wave["rows"][binding["slot_index"]]
    _require(row.get("ordinal") == ordinal and row.get("attempt_start_sha256") == _hash(_attempt_path(root, ordinal, "attempt-start.json").read_bytes())
             and row.get("context_sha256") == start.get("context_sha256"), "Suffix wave row ownership differs")
    settlement_path = _wave_path(root, binding["start_ordinal"], binding["wave_size"], "settlement")
    _require(settlement_path.is_file(), "Suffix wave settlement is absent")
    settlement = _json(settlement_path.read_bytes(), "Suffix wave settlement")
    _require(settlement.get("epoch_sha256") == epoch_sha256 and settlement.get("wave_start_sha256") == _hash(raw)
             and isinstance(settlement.get("rows"), list) and len(settlement["rows"]) == binding["wave_size"],
             "Suffix wave settlement binding differs")
    for offset, settled in enumerate(settlement["rows"]):
        expected_ordinal = binding["start_ordinal"] + offset
        terminal_path = _attempt_path(root, expected_ordinal, "terminal.json")
        _require(isinstance(settled, Mapping) and settled.get("ordinal") == expected_ordinal
                 and settled.get("status") == "completed" and terminal_path.is_file()
                 and settled.get("terminal_sha256") == _hash(terminal_path.read_bytes()),
                 "Suffix wave is not fully settled")


def admit_wave(
    *, suffix_root: Path | str, expected_epoch_sha256: str, start_ordinal: int, wave_size: int,
    approved_v5_routes: Mapping[str, Any], protected_native_identities: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Read-only strict replay of one settled wave and its protected identity boundary."""
    root = _plain(suffix_root, directory=True)
    epoch_sha256 = _sha(expected_epoch_sha256, "Suffix epoch")
    epoch, before_epoch = _load_epoch(root, epoch_sha256)
    plan_root, old_root, prefix_root, requests = _epoch_integrity(root, epoch)
    before_root, before_old, before_prefix = _inventory(root), _inventory(old_root), _inventory(prefix_root)
    wave, wave_raw = _wave_start(root, epoch_sha256=epoch_sha256, start_ordinal=start_ordinal, wave_size=wave_size)
    _require(wave.get("epoch_source_sha256") == _hash(before_epoch) and wave.get("execution_mode") == epoch["execution_mode"]
             and wave.get("max_concurrency") == epoch["max_concurrency"]
             and wave.get("runtime_manifest_sha256") == epoch["runtime_manifest"]["sha256"]
             and wave.get("runtime_package_manifest_sha256") == epoch["runtime_package"]["manifest_sha256"]
             and wave.get("v3_sha256") == epoch["v3_source"]["sha256"], "Suffix wave epoch binding differs")
    review_record = wave.get("review")
    _require(isinstance(review_record, Mapping) and set(review_record) == {"path", "sha256"}, "Suffix wave review differs")
    review = _review(_plain(review_record["path"], directory=False), _sha(review_record["sha256"], "Suffix wave review"),
                     epoch_sha256=epoch_sha256, epoch=epoch, live=False)
    _require(review["route_sha256"] == wave.get("route_sha256") and review["gate_sha256"] == wave.get("gate_sha256"),
             "Suffix wave route binding differs")
    settlement_path = _wave_path(root, start_ordinal, wave_size, "settlement")
    settlement = _json(settlement_path.read_bytes(), "Suffix wave settlement")
    _require(settlement.get("epoch_sha256") == epoch_sha256 and settlement.get("wave_start_sha256") == _hash(wave_raw)
             and settlement.get("start_ordinal") == start_ordinal and settlement.get("wave_size") == wave_size
             and isinstance(settlement.get("rows"), list) and len(settlement["rows"]) == wave_size,
             "Suffix wave settlement binding differs")
    runtime, plan = _runtime_from_epoch(epoch), _plan(plan_root, epoch["plan_sha256"])[0]
    passes, identities = _pass_index(plan), []
    protected = [dict(item) for item in protected_native_identities]
    protected_requests = [item.get("request_id_hash") for item in protected]
    protected_sessions = [item.get("session_id_hash") for item in protected]
    _require(all(isinstance(value, str) and _HASH.fullmatch(value) for value in protected_requests + protected_sessions)
             and len(protected_requests) == len(set(protected_requests)) and len(protected_sessions) == len(set(protected_sessions)),
             "Protected native identity boundary differs")
    for expected, wave_row in zip(range(start_ordinal, start_ordinal + wave_size), wave["rows"], strict=True):
        row = requests[expected]
        start_path, terminal_path = _attempt_path(root, expected, "attempt-start.json"), _attempt_path(root, expected, "terminal.json")
        _require(wave_row.get("attempt_start_sha256") == _hash(start_path.read_bytes())
                 and wave_row.get("context_sha256") == _json(start_path.read_bytes(), "Suffix attempt start").get("context_sha256")
                 and wave_row.get("source_sha256") == _source_for_pass(plan_root, passes[row["pass_id"]])["sha256"],
                 "Suffix wave row binding differs")
        settled = settlement["rows"][expected - start_ordinal]
        _require(settled.get("ordinal") == expected and settled.get("status") == "completed"
                 and settled.get("terminal_sha256") == _hash(terminal_path.read_bytes()), "Suffix wave is not fully settled")
        _verdicts, identity = _replay_suffix_terminal(root=root, epoch_sha256=epoch_sha256, epoch=epoch, runtime=runtime,
                                                     plan_root=plan_root, passed=passes[row["pass_id"]], row=row,
                                                     approved_v5_routes=approved_v5_routes)
        _require(settled.get("native_identity") == identity, "Suffix wave settlement identity differs")
        identities.append(identity)
    all_request_ids = protected_requests + [item["request_id_hash"] for item in identities]
    all_session_ids = protected_sessions + [item["session_id_hash"] for item in identities]
    _require(len(all_request_ids) == len(set(all_request_ids)) and len(all_session_ids) == len(set(all_session_ids)),
             "Wave overlaps protected native identities")
    _completed_v5_identities(root, epoch_sha256)
    runtime.verify()
    _epoch_integrity(root, epoch)
    _require(_epoch_path(root).read_bytes() == before_epoch and _inventory(root) == before_root
             and _inventory(old_root) == before_old and _inventory(prefix_root) == before_prefix,
             "Read-only wave admission changed evidence")
    return {"start_ordinal": start_ordinal, "wave_size": wave_size, "native_identities": identities,
            "provider_calls_made": 0}


def _old_prefix_native_identities(
    *,
    epoch: Mapping[str, Any],
    plan_root: Path,
    plan: Mapping[str, Any],
    recovered: ModuleType,
    old_runtime: Any,
    approved_v4_routes: Mapping[str, Any],
    mixed_prefix: Mapping[str, Any],
) -> list[dict[str, str]]:
    """Reconstruct all 79 old native identities; ordinal 70 remains non-native."""
    manifest_path = _plain(epoch["old_prefix_manifest"]["path"], directory=False)
    manifest = _json(_read(manifest_path, epoch["old_prefix_manifest"]["sha256"], "Old prefix manifest"), "Old prefix manifest")
    _require(
        manifest.get("native_identity_commitment_fields") == ["request_id_hash", "session_id_hash", "observed_turns"]
        and manifest.get("native_identity_commitment_sha256") == OLD_PREFIX_NATIVE_IDENTITY_COMMITMENT_SHA256
        and manifest.get("unique_native_request_ids") == 79 and manifest.get("unique_native_session_ids") == 79,
        "Old prefix native identity commitment differs",
    )
    records = manifest.get("per_pass")
    _require(isinstance(records, list) and len(records) == 4 and all(isinstance(item, Mapping) for item in records),
             "Old prefix pass identity inventory differs")
    passes = _pass_index(plan)
    native = recovered._module("native_admission")
    identities: list[dict[str, str]] = []
    for record in records[:3]:
        pass_id = record.get("pass_id")
        passed = passes.get(pass_id)
        run_root = _plain(record.get("run_root"), directory=True)
        _require(
            isinstance(passed, Mapping) and record.get("checkpoint_count") == FULL_PASS_BATCHES
            and record.get("native_records") == FULL_PASS_BATCHES and record.get("study_recovered_records") == 0,
            "Old native pass identity binding differs",
        )
        replay = native.admit_pass(
            run_root, source=_source_for_pass(plan_root, passed), batch_size=DISPATCH_BATCH_SIZE,
            approved_routes=dict(approved_v4_routes), runtime=old_runtime,
        )
        values = replay.get("native_identities") if isinstance(replay, Mapping) else None
        _require(isinstance(values, list) and len(values) == FULL_PASS_BATCHES, "Old native pass replay differs")
        identities.extend(dict(item) for item in values if isinstance(item, Mapping))
    partial = records[3]
    _require(
        partial.get("run_root") == epoch["old_prefix_run_root"] and partial.get("checkpoint_count") == PREFIX_BATCHES
        and partial.get("native_records") == 10 and partial.get("study_recovered_records") == 1,
        "Old recovered prefix identity binding differs",
    )
    recovered_identities = mixed_prefix.get("native_identities")
    _require(isinstance(recovered_identities, list) and len(recovered_identities) == 10, "Recovered prefix native identity replay differs")
    identities.extend(dict(item) for item in recovered_identities if isinstance(item, Mapping))
    request_ids = [item.get("request_id_hash") for item in identities]
    session_ids = [item.get("session_id_hash") for item in identities]
    _require(
        len(identities) == 79 and len(set(request_ids)) == 79 and len(set(session_ids)) == 79
        and all(set(item) >= {"request_id_hash", "session_id_hash", "observed_turns"}
                and type(item.get("observed_turns")) is int and item["observed_turns"] >= 1 for item in identities)
        and all(isinstance(value, str) and _HASH.fullmatch(value) for value in request_ids + session_ids),
        "Full old native identity replay differs",
    )
    return [{"request_id_hash": item["request_id_hash"], "session_id_hash": item["session_id_hash"]} for item in identities]


def _qualified_score(score: Any) -> tuple[int | float, int | float]:
    final = score.get("final_score") if isinstance(score, Mapping) else None
    observed = final.get("observed") if isinstance(final, Mapping) else None
    coverage = score.get("coverage") if isinstance(score, Mapping) else None
    score_contract = score.get("fail_contract") if isinstance(score, Mapping) else None
    final_contract = final.get("fail_contract") if isinstance(final, Mapping) else None
    _require(
        isinstance(score, Mapping) and isinstance(final, Mapping)
        and score.get("provisional") is not True and score_contract is not True and score_contract not in ("failed", "fail")
        and final.get("provisional") is not True and final_contract is not True and final_contract not in ("failed", "fail")
        and type(observed) in (int, float) and math.isfinite(observed) and 0 <= observed <= 100
        and type(coverage) in (int, float) and math.isfinite(coverage) and coverage >= 0.88,
        "Canonical score is not qualified",
    )
    return observed, coverage


def admit_pass(
    *,
    suffix_root: Path | str,
    expected_epoch_sha256: str,
    pass_id: str,
    approved_v4_routes: Mapping[str, Any],
    approved_v5_routes: Mapping[str, Any],
) -> dict[str, Any]:
    """Replay a complete mixed pass without writing evidence or contacting a provider."""
    root = _plain(suffix_root, directory=True)
    epoch_sha256 = _sha(expected_epoch_sha256, "Suffix epoch")
    epoch, before_epoch = _load_epoch(root, epoch_sha256)
    plan_root, old_root, prefix_root, _requests = _epoch_integrity(root, epoch)
    before_old, before_prefix, before_suffix = _inventory(old_root), _inventory(prefix_root), _inventory(root)
    plan, _ = _plan(plan_root, epoch["plan_sha256"])
    passed = _pass_index(plan).get(pass_id)
    _require(isinstance(passed, Mapping), "Requested mixed pass is absent")
    rows, mixed_prefix = _pass_requests(plan, pass_id)
    runtime = _runtime_from_epoch(epoch)
    expected_ids = [item["question"]["id"] for item in runtime.questions]
    _require(len(expected_ids) == 178, "v5 runtime question inventory differs")
    source = _source_for_pass(plan_root, passed)
    old_runtime = _old_runtime_from_epoch(epoch)
    old_ids = [item["question"]["id"] for item in old_runtime.questions]
    _require(expected_ids == old_ids, "Old and v5 runtime question inventories differ")
    recovered = _load_module(
        _plain(epoch["recovered_study_source"]["path"], directory=False),
        epoch["recovered_study_source"]["sha256"],
        "_dryad_v5_recovered_",
    )
    old_manifest = _json(_read(_plain(epoch["old_prefix_manifest"]["path"], directory=False), epoch["old_prefix_manifest"]["sha256"], "Old prefix manifest"), "Old prefix manifest")
    old_records = old_manifest.get("per_pass")
    _require(isinstance(old_records, list) and len(old_records) == 4 and isinstance(old_records[3], Mapping), "Old prefix pass inventory differs")
    old_prefix_pass = _pass_index(plan).get(old_records[3].get("pass_id"))
    _require(isinstance(old_prefix_pass, Mapping), "Old recovered pass plan binding differs")
    old = recovered.admit_prefix(
        prefix_root,
        source=_source_for_pass(plan_root, old_prefix_pass),
        batch_size=DISPATCH_BATCH_SIZE,
        approved_routes=dict(approved_v4_routes),
        expected_batches=PREFIX_BATCHES,
        expected_recovered_manifest_sha256=epoch["recovered_study_manifest"]["sha256"],
        expected_adoption_sha256=epoch["recovery_adoption_sha256"],
        expected_amendment_sha256=epoch["recovery_amendment_sha256"],
        runtime=old_runtime,
    )
    _require(
        isinstance(old, Mapping) and old.get("evidence_class") == "mixed_native_and_study_recovered_record_replay"
        and old.get("native_record_count") == 10 and old.get("study_recovered_record_count") == 1
        and old.get("study_recovered_ordinals") == [70] and len(old.get("verdicts", [])) == 88
        and len(old.get("native_identities", [])) == 10,
        "Old mixed prefix admission differs",
    )
    old_prefix_identities = _old_prefix_native_identities(
        epoch=epoch, plan_root=plan_root, plan=plan, recovered=recovered, old_runtime=old_runtime,
        approved_v4_routes=approved_v4_routes, mixed_prefix=old,
    )
    suffix_verdicts: list[dict[str, Any]] = []
    suffix_identities: list[dict[str, str]] = []
    for row in rows[PREFIX_BATCHES if mixed_prefix else 0:]:
        _require_wave_settlement(root, epoch_sha256=epoch_sha256, ordinal=row["ordinal"])
        verdicts, identity = _replay_suffix_terminal(
            root=root, epoch_sha256=epoch_sha256, epoch=epoch, runtime=runtime, plan_root=plan_root,
            passed=passed, row=row, approved_v5_routes=approved_v5_routes,
        )
        suffix_verdicts.extend(verdicts)
        suffix_identities.append(identity)
    combined = ([dict(item) for item in old["verdicts"]] if mixed_prefix else []) + suffix_verdicts
    _require(
        len(combined) == len(expected_ids) and [item.get("question_id") for item in combined] == expected_ids,
        "Pass verdict order or coverage differs",
    )
    all_request_ids = [item.get("request_id_hash") for item in suffix_identities]
    all_session_ids = [item.get("session_id_hash") for item in suffix_identities]
    _require(
        len(suffix_identities) == (12 if mixed_prefix else FULL_PASS_BATCHES)
        and len(set(all_request_ids)) == len(all_request_ids) and len(set(all_session_ids)) == len(all_session_ids)
        and all(isinstance(value, str) and _HASH.fullmatch(value) for value in all_request_ids + all_session_ids),
        "Pass native identity collision",
    )
    global_v5 = _completed_v5_identities(root, epoch_sha256)
    old_request_ids = {item["request_id_hash"] for item in old_prefix_identities}
    old_session_ids = {item["session_id_hash"] for item in old_prefix_identities}
    v5_request_ids = {item["request_id_hash"] for item in global_v5}
    v5_session_ids = {item["session_id_hash"] for item in global_v5}
    _require(
        (not (old_request_ids & v5_request_ids)) and (not (old_session_ids & v5_session_ids)),
        "v5 pass overlaps old native identities",
    )
    score = runtime.core.score_bundle(runtime.modules, runtime.bundle, combined,
                                       artifact_id=source["opaque_story_id"], task_contract=None)
    observed, coverage = _qualified_score(score)
    runtime.verify()
    old_runtime.verify()
    _epoch_integrity(root, epoch)
    _require(
        _epoch_path(root).read_bytes() == before_epoch and _inventory(old_root) == before_old
        and _inventory(prefix_root) == before_prefix and _inventory(root) == before_suffix,
        "Read-only mixed replay changed evidence",
    )
    return {
        "pass_id": pass_id,
        "evidence_class": "mixed_v4_native_recovered70_and_v5_native_replay" if mixed_prefix else "v5_native_full_pass_replay",
        "verdicts": [{"question_id": item["question_id"], "verdict": item["verdict"]} for item in combined],
        "score": observed,
        "coverage": coverage,
        "old_prefix_native_records": 79,
        "old_v4_native_records": 10 if mixed_prefix else 0,
        "old_recovered70_records": 1 if mixed_prefix else 0,
        "new_v5_native_records": len(suffix_identities),
        "native_identities": old_prefix_identities + suffix_identities,
        "provider_calls_made": 0,
    }
