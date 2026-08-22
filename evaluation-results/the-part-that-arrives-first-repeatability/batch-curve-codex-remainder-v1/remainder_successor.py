"""Seal and inspect the quota-stopped batch-curve remainder without calling a provider."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Mapping


HERE = Path(__file__).resolve().parent
CONTRACT_PATH = HERE / "remainder-contract.json"
PREPARATION = "remainder-preparation.json"
PREFLIGHT = "current-quota-preflight.json"
PARENT_PUBLIC = "C:/Users/Haile/Documents/cwr-batch-curve-codex-v1-20260821-ae23440-r1"
PARENT_PRIVATE = "C:/Users/Haile/Documents/cwr-batch-curve-codex-v1-20260821-ae23440-private-r1"


def _json_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected object: {path}")
    return value


def _atomic(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_bytes(_json_bytes(value) + b"\n")
    temporary.replace(path)


def _time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError("Timestamp requires an explicit offset")
    return parsed


def _root_sha(path: Path) -> str:
    return hashlib.sha256(str(path.resolve()).encode("utf-8")).hexdigest()


def _overlap(left: Path, right: Path) -> bool:
    first, second = left.resolve(), right.resolve()
    return first == second or first in second.parents or second in first.parents


def _names(directory: Path) -> set[str]:
    if not directory.is_dir():
        raise ValueError(f"Expected directory: {directory}")
    return {path.name for path in directory.iterdir()}


def contract() -> dict[str, Any]:
    value = _read(CONTRACT_PATH)
    required = {"format_version", "study_id", "status", "closed_parent", "remainder", "quota_gate"}
    if set(value) != required or value["format_version"] != 1 or value["study_id"] != "the-part-that-arrives-first-batch-curve-codex-remainder-v1":
        raise ValueError("Remainder contract shape drifted")
    if value["status"] != "preregistered_remainder_no_live_executor":
        raise ValueError("Remainder must remain a no-live-executor preregistration")
    parent = value["closed_parent"]
    if parent.get("git_commit") != "ae234403707f2005383188a185123d7a85a16002" or parent.get("public_root") != PARENT_PUBLIC or parent.get("private_root") != PARENT_PRIVATE:
        raise ValueError("Closed parent identity drifted")
    if set(parent) != {"git_commit", "public_root", "private_root", "preexecution_receipt", "claims", "completed_cells", "partial_cell"}:
        raise ValueError("Closed parent shape drifted")
    if parent["claims"] != {"relative_directory": "claims", "expected_names": []}:
        raise ValueError("Closed claims lineage drifted")
    completed, partial = parent["completed_cells"], parent["partial_cell"]
    if completed != {"count": 35, "relative_directory": "cells", "manifest_sha256": completed.get("manifest_sha256")} or not isinstance(completed["manifest_sha256"], str) or len(completed["manifest_sha256"]) != 64:
        raise ValueError("Completed parent geometry drifted")
    if set(partial) != {"sequence", "size", "repetition", "public_checkpoint", "private_run", "private_tree", "accepted_prefix", "quota_rejections"} or (partial["sequence"], partial["size"], partial["repetition"]) != (36, 4, 3):
        raise ValueError("Partial parent identity drifted")
    prefix, rejected, tree = partial["accepted_prefix"], partial["quota_rejections"], partial["private_tree"]
    if set(prefix) != {"batch_start", "batch_end", "manifest_sha256"} or prefix.get("batch_start") != 1 or prefix.get("batch_end") != 31 or not isinstance(prefix.get("manifest_sha256"), str) or len(prefix["manifest_sha256"]) != 64:
        raise ValueError("Accepted-prefix bounds drifted")
    if set(rejected) != {"batch", "attempts", "manifest_sha256", "retry_after"} or rejected.get("batch") != 32 or rejected.get("attempts") != 3 or rejected.get("retry_after") != value["quota_gate"].get("not_before") or not isinstance(rejected.get("manifest_sha256"), str) or len(rejected["manifest_sha256"]) != 64:
        raise ValueError("Quota-rejection lineage drifted")
    if set(tree) != {"relative_directory", "file_count", "manifest_sha256"} or tree.get("relative_directory") != "runs/cell-36" or tree.get("file_count") != 163 or not isinstance(tree.get("manifest_sha256"), str) or len(tree["manifest_sha256"]) != 64:
        raise ValueError("Partial private-tree lineage drifted")
    cells = value["remainder"].get("cells")
    expected_cells = [
        {"parent_cell": 36, "size": 4, "repetition": 3, "batch_start": 32, "batch_end": 45},
        {"parent_cell": 37, "size": 32, "repetition": 3, "batch_start": 1, "batch_end": 6},
        {"parent_cell": 38, "size": 8, "repetition": 3, "batch_start": 1, "batch_end": 23},
        {"parent_cell": 39, "size": 48, "repetition": 3, "batch_start": 1, "batch_end": 4},
    ]
    if set(value["remainder"]) != {"question_count", "cells", "scheduled_provider_calls", "prohibitions"} or not isinstance(cells, list) or cells != expected_cells:
        raise ValueError("Remainder geometry drifted")
    if value["remainder"].get("question_count") != 178 or value["remainder"].get("scheduled_provider_calls") != 47 or value["remainder"].get("prohibitions") != ["no_in_place_resume", "no_repeat_of_parent_cell_36_batches_1_through_31", "no_provider_call_from_this_package"]:
        raise ValueError("Remainder provider-call boundary drifted")
    if set(value["quota_gate"]) != {"not_before", "required_record", "required_availability", "evidence_class", "max_age_minutes"} or value["quota_gate"].get("required_record") != PREFLIGHT or value["quota_gate"].get("required_availability") != "available" or value["quota_gate"].get("evidence_class") != "operator_observed_current_quota_preflight" or value["quota_gate"].get("max_age_minutes") != 15:
        raise ValueError("Quota gate shape drifted")
    _time(str(value["quota_gate"]["not_before"]))
    return value


def _manifest(root: Path, relative_paths: list[str]) -> str:
    material = b"".join(
        f"{relative}\0{(root / relative).stat().st_size}\0{_sha(root / relative)}\n".encode("utf-8")
        for relative in relative_paths
    )
    return hashlib.sha256(material).hexdigest()


def _bound(root: Path, binding: Mapping[str, Any]) -> None:
    if set(binding) != {"relative_path", "bytes", "sha256"} or not isinstance(binding["relative_path"], str) or type(binding["bytes"]) is not int or not isinstance(binding["sha256"], str) or len(binding["sha256"]) != 64:
        raise ValueError("Closed parent binding shape drifted")
    path = root / str(binding["relative_path"])
    if not path.is_file() or path.stat().st_size != binding["bytes"] or _sha(path) != binding["sha256"]:
        raise ValueError(f"Closed parent binding drifted: {binding['relative_path']}")


def _validate_committed_private_evidence(public: Path, private: Path, cell: int) -> None:
    checkpoint = _read(public / "cells" / f"cell-{cell:02d}.json")
    calls = checkpoint.get("calls")
    if checkpoint.get("status") != "completed" or not isinstance(calls, list) or len(calls) != 2 or calls[0] != {"event": "attempt_started", "attempt": 1} or not isinstance(calls[1], dict):
        raise ValueError("Closed completed-cell checkpoint drifted")
    raw = calls[1].get("raw_evidence_index")
    expected_relative = f"evidence-index/cell-{cell:02d}.json"
    if not isinstance(raw, dict) or set(raw) != {"private_root_sha256", "relative_path", "bytes", "sha256"} or raw.get("private_root_sha256") != _root_sha(private) or raw.get("relative_path") != expected_relative:
        raise ValueError("Closed raw-evidence reference drifted")
    _bound(private, {"relative_path": expected_relative, "bytes": raw["bytes"], "sha256": raw["sha256"]})
    index = _read(private / expected_relative)
    run_relative = f"runs/cell-{cell:02d}"
    if set(index) != {"format_version", "private_root_sha256", "run_path", "files"} or index.get("format_version") != 1 or index.get("private_root_sha256") != _root_sha(private) or index.get("run_path") != run_relative or not isinstance(index.get("files"), list) or not index["files"]:
        raise ValueError("Closed raw-evidence index drifted")
    expected: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in index["files"]:
        if not isinstance(item, dict) or set(item) != {"path", "bytes", "sha256"} or not isinstance(item["path"], str) or type(item["bytes"]) is not int or not isinstance(item["sha256"], str) or len(item["sha256"]) != 64 or item["path"] in seen or not item["path"].startswith(run_relative + "/"):
            raise ValueError("Closed raw-evidence membership drifted")
        seen.add(item["path"])
        path = private / item["path"]
        if not path.is_file() or path.stat().st_size != item["bytes"] or _sha(path) != item["sha256"]:
            raise ValueError("Closed raw-evidence file drifted")
        expected.append(item)
    actual = [{"path": path.relative_to(private).as_posix(), "bytes": path.stat().st_size, "sha256": _sha(path)} for path in sorted((private / run_relative).rglob("*")) if path.is_file()]
    if actual != expected:
        raise ValueError("Closed raw-evidence membership changed")


def validate_closed_parent() -> dict[str, Any]:
    """Validate the immutable predecessor geometry; this is local filesystem work."""
    value = contract(); parent = value["closed_parent"]
    public, private = Path(parent["public_root"]).resolve(), Path(parent["private_root"]).resolve()
    if not public.is_dir() or not private.is_dir() or _overlap(public, private):
        raise ValueError("Closed parent roots are unavailable or not disjoint")
    if _names(public) != {"cells", "claims", "preexecution-disclosure-receipt.json"} or _names(private) != {"evidence-index", "runs"}:
        raise ValueError("Closed parent top-level membership drifted")
    if _names(public / parent["claims"]["relative_directory"]) != set(parent["claims"]["expected_names"]):
        raise ValueError("Closed claims membership drifted")
    _bound(public, parent["preexecution_receipt"])
    partial = parent["partial_cell"]
    _bound(public, partial["public_checkpoint"]); _bound(private, partial["private_run"])
    completed = [f"cells/cell-{number:02d}.json" for number in range(1, 36)]
    if _names(public / "cells") != {Path(relative).name for relative in [*completed, "cells/cell-36.json"]}:
        raise ValueError("Closed public cell membership drifted")
    if _names(private / "evidence-index") != {f"cell-{number:02d}.json" for number in range(1, 36)} or _names(private / "runs") != {f"cell-{number:02d}" for number in range(1, 37)}:
        raise ValueError("Closed private cell membership drifted")
    if _manifest(public, completed) != parent["completed_cells"]["manifest_sha256"]:
        raise ValueError("Closed completed-cell manifest drifted")
    for relative in completed:
        if _read(public / relative).get("status") != "completed":
            raise ValueError("Closed completed-cell geometry drifted")
    for cell in range(1, 36):
        _validate_committed_private_evidence(public, private, cell)
    partial_checkpoint = _read(public / "cells/cell-36.json")
    if partial_checkpoint != {"format_version": 1, "plan": partial_checkpoint.get("plan"), "calls": [{"event": "attempt_started", "attempt": 1}], "status": "in_progress"} or not isinstance(partial_checkpoint["plan"], dict) or partial_checkpoint["plan"].get("sequence") != 36 or partial_checkpoint["plan"].get("size") != 4 or partial_checkpoint["plan"].get("repetition") != 3:
        raise ValueError("Closed partial-cell checkpoint drifted")
    prefix = [f"runs/cell-36/responses/batch-{number:04d}.json" for number in range(1, 32)]
    if _manifest(private, prefix) != partial["accepted_prefix"]["manifest_sha256"]:
        raise ValueError("Closed accepted-prefix manifest drifted")
    rejected = [f"runs/cell-36/responses/rejected/batch-0032/attempt-{number:04d}.json" for number in range(1, 4)]
    if _manifest(private, rejected) != partial["quota_rejections"]["manifest_sha256"]:
        raise ValueError("Closed quota-rejection manifest drifted")
    tree_files = [path for path in sorted((private / partial["private_tree"]["relative_directory"]).rglob("*")) if path.is_file()]
    tree_relative = [path.relative_to(private).as_posix() for path in tree_files]
    if len(tree_relative) != partial["private_tree"]["file_count"] or _manifest(private, tree_relative) != partial["private_tree"]["manifest_sha256"]:
        raise ValueError("Closed partial-cell tree membership drifted")
    responses = private / "runs/cell-36/responses"
    if (responses / "batch-0032.json").exists() or any(responses.glob("batch-0032.accepted-*")) or any(responses.glob("batch-0032.attempt-*.message.*")):
        raise ValueError("Closed partial cell has later accepted work")
    run = _read(private / "runs/cell-36/run.json")
    if run.get("batch_size") != 4 or run.get("batch_attempts") != 3 or run.get("provider") != {"configured": "codex", "reported": "openai", "model": "gpt-5.6-sol", "reasoning": "high"} or not isinstance(run.get("question_ids"), list) or len(run["question_ids"]) != 178 or len(set(run["question_ids"])) != 178:
        raise ValueError("Closed partial-run identity drifted")
    for attempt, relative in enumerate(rejected, 1):
        record = _read(private / relative)
        if record.get("batch") != 32 or record.get("attempt") != attempt or record.get("sequence") != attempt or record.get("retryable") is not True or record.get("stage") != "provider_transport" or "Aug 27th, 2026 7:21 PM" not in str(record.get("error", {}).get("message", "")):
            raise ValueError("Closed quota-rejection detail drifted")
    return {"public_root_sha256": _root_sha(public), "private_root_sha256": _root_sha(private), "completed_cells": 35, "accepted_parent_batches": 31, "quota_rejections": 3}


def schedule() -> list[dict[str, int]]:
    """Return only work absent from the closed parent; batches are one-indexed."""
    rows: list[dict[str, int]] = []
    for cell in contract()["remainder"]["cells"]:
        for batch in range(int(cell["batch_start"]), int(cell["batch_end"]) + 1):
            rows.append({"parent_cell": int(cell["parent_cell"]), "size": int(cell["size"]), "repetition": int(cell["repetition"]), "batch": batch})
    if len(rows) != 47 or len({(row["parent_cell"], row["batch"]) for row in rows}) != len(rows) or any(row["parent_cell"] == 36 and row["batch"] <= 31 for row in rows):
        raise ValueError("Remainder schedule duplicated completed work")
    return rows


def _validate_fresh_roots(work_root: Path, private_root: Path) -> None:
    work, private = work_root.resolve(), private_root.resolve()
    parent = contract()["closed_parent"]
    protected = [Path(parent["public_root"]).resolve(), Path(parent["private_root"]).resolve(), HERE.parents[2].resolve()]
    if _overlap(work, private) or any(_overlap(root, protected_root) for root in (work, private) for protected_root in protected):
        raise ValueError("Successor roots must be fresh and disjoint from each other and the closed parent")
    for root in (work, private):
        if root.exists():
            raise ValueError("Successor roots must be fresh and empty before preparation")


def prepare(work_root: Path, private_root: Path) -> dict[str, Any]:
    """Seal fresh roots and the closed-parent proof. This function has no provider client."""
    _validate_fresh_roots(work_root, private_root)
    lineage = validate_closed_parent()
    work_root.mkdir(parents=True, exist_ok=False); private_root.mkdir(parents=True, exist_ok=False)
    receipt = {"format_version": 1, "study_id": contract()["study_id"], "contract_sha256": _sha(CONTRACT_PATH), "module_sha256": _sha(Path(__file__)), "work_root_sha256": _root_sha(work_root), "private_root_sha256": _root_sha(private_root), "lineage": lineage, "schedule_sha256": hashlib.sha256(_json_bytes(schedule())).hexdigest(), "scheduled_provider_calls": len(schedule()), "quota_gate": contract()["quota_gate"], "provider_calls_made": 0}
    _atomic(work_root / PREPARATION, receipt)
    return receipt


def record_current_quota_preflight(work_root: Path, *, checked_at: str, availability: str, note: str) -> dict[str, Any]:
    """Record operator-observed quota state; it never performs the quota check itself."""
    value = contract(); threshold = _time(value["quota_gate"]["not_before"]); checked = _time(checked_at)
    if checked < threshold:
        raise ValueError("Quota preflight is before the provider's retry-after time")
    if availability != value["quota_gate"]["required_availability"] or not note.strip():
        raise ValueError("Quota preflight must explicitly record current availability")
    preparation = _read(work_root / PREPARATION)
    if preparation.get("contract_sha256") != _sha(CONTRACT_PATH) or preparation.get("provider_calls_made") != 0:
        raise ValueError("Fresh preparation receipt drifted")
    record = {"format_version": 1, "study_id": value["study_id"], "checked_at": checked_at, "availability": availability, "evidence_class": value["quota_gate"]["evidence_class"], "note": note}
    target = work_root / PREFLIGHT
    if target.exists() and _read(target) != record:
        raise ValueError("Current quota preflight is immutable once recorded")
    _atomic(target, record)
    return record


def live_eligible(work_root: Path, private_root: Path, *, now: str) -> bool:
    """Gate a future, separately reviewed executor; this package cannot send requests."""
    value = contract()
    if _time(now) < _time(value["quota_gate"]["not_before"]):
        return False
    try:
        _validate_successor_receipt(work_root, private_root)
    except (OSError, ValueError, KeyError, TypeError):
        return False
    path = work_root / PREFLIGHT
    if not path.is_file():
        return False
    record = _read(path)
    expected = {"format_version": 1, "study_id": value["study_id"], "checked_at": record.get("checked_at"), "availability": "available", "evidence_class": value["quota_gate"]["evidence_class"], "note": record.get("note")}
    if record != expected or not isinstance(record["checked_at"], str) or not isinstance(record["note"], str) or not record["note"].strip():
        return False
    checked, observed_now = _time(record["checked_at"]), _time(now)
    return _time(value["quota_gate"]["not_before"]) <= checked <= observed_now <= checked + timedelta(minutes=value["quota_gate"]["max_age_minutes"])


def _validate_successor_receipt(work_root: Path, private_root: Path) -> None:
    _validate_fresh_pair(work_root, private_root)
    value = contract()
    if _names(work_root) != {PREPARATION, PREFLIGHT} or _names(private_root) != set():
        raise ValueError("Prepared successor root membership drifted")
    receipt = _read(work_root / PREPARATION)
    expected = {"format_version": 1, "study_id": value["study_id"], "contract_sha256": _sha(CONTRACT_PATH), "module_sha256": _sha(Path(__file__)), "work_root_sha256": _root_sha(work_root), "private_root_sha256": _root_sha(private_root), "lineage": validate_closed_parent(), "schedule_sha256": hashlib.sha256(_json_bytes(schedule())).hexdigest(), "scheduled_provider_calls": 47, "quota_gate": value["quota_gate"], "provider_calls_made": 0}
    if receipt != expected:
        raise ValueError("Preparation receipt no longer binds the exact successor")


def _validate_fresh_pair(work_root: Path, private_root: Path) -> None:
    work, private = work_root.resolve(), private_root.resolve()
    parent = contract()["closed_parent"]
    protected = [Path(parent["public_root"]).resolve(), Path(parent["private_root"]).resolve(), HERE.parents[2].resolve()]
    if not work.is_dir() or not private.is_dir() or _overlap(work, private) or any(_overlap(root, protected_root) for root in (work, private) for protected_root in protected):
        raise ValueError("Successor roots are not a disjoint prepared pair")
