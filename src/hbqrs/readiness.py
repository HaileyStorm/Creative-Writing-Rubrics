"""Read scorer readiness from saved long-form score parents without rewriting them."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from .core import HBQError
from .longform import _schema, _validate_schema, normalize_score_result


def _read_json(path: Path) -> tuple[bytes, Mapping[str, Any]]:
    try:
        payload = path.read_bytes()
    except OSError as exc:
        raise HBQError(f"Cannot read saved JSON: {path}") from exc
    try:
        value = json.loads(payload)
    except (ValueError, UnicodeDecodeError) as exc:
        raise HBQError(f"Invalid saved JSON: {path}") from exc
    if not isinstance(value, Mapping):
        raise HBQError(f"Saved JSON must be an object: {path}")
    return payload, value


def workflow_scorer_readiness(output_dir: str | Path) -> dict[str, Any]:
    """Derive a non-persisted, source-bound view; missing historical status is unknown."""
    directory = Path(output_dir)
    report_bytes, report = _read_json(directory / "report.json")
    _validate_schema(report, _schema("hbq_long_form_workflow_report.schema.json"), "Long-form workflow report")
    route = report["route"]
    results = report["local_results"]
    local_by_id = {result["scope_id"]: result for result in results}
    if len(local_by_id) != len(results) or set(local_by_id) != set(route["local_unit_ids"]):
        raise HBQError("Report local results do not match selected unit IDs")
    if report["global_result"] is not None and report["global_result"]["scope_id"] != "work":
        raise HBQError("Report global result does not identify the whole work")
    artifact_id = report["artifact"]["artifact_id"]
    scopes = [("work", "global", report["global_result"], artifact_id, route["global_bundle_id"])]
    scopes.extend(
        (unit_id, unit_id, local_by_id[unit_id], f"{artifact_id}-{unit_id}", route["local_bundle_id"])
        for unit_id in route["local_unit_ids"]
    )
    output = []
    for scope_id, folder, result, expected_artifact, expected_bundle in scopes:
        item = {"scope_id": scope_id, "control_state": result["control_state"] if result else None,
                "scorer_status": None, "source_score_sha256": None, "reason": None}
        source = directory / ".private" / "evaluations" / folder / "score.json"
        if result is None:
            item["reason"] = "report_has_no_score"
        else:
            try:
                source.lstat()
            except FileNotFoundError:
                item["reason"] = "source_score_missing"
                output.append(item)
                continue
            except OSError as exc:
                raise HBQError(f"Cannot inspect saved score: {source}") from exc
            payload, score = _read_json(source)
            _validate_schema(score, _schema("hbq_score_report.schema.json"), "Saved score report")
            if score.get("artifact_id") != expected_artifact or score.get("bundle_id") != expected_bundle:
                raise HBQError(f"Saved score identity differs from workflow report: {source}")
            # Normalize raw scoring fields, never the shortcut for a mapping
            # carrying already-normalized aliases alongside those fields.
            raw_score = {key: value for key, value in score.items() if key not in {"control_state", "score"}}
            normalized = normalize_score_result(raw_score, scope_id=scope_id, label=result["label"])
            # Historical v1 reports could omit optional fields that newer
            # normalizers include; compare every field actually recorded.
            if any(key not in normalized or normalized[key] != value for key, value in result.items()):
                raise HBQError(f"Saved score differs from workflow report: {source}")
            item["source_score_sha256"] = hashlib.sha256(payload).hexdigest()
            if "status" not in score:
                item["reason"] = "scorer_status_missing"
            else:
                status = score["status"]
                allowed = {"VALID": {"SCORED", "PROVISIONAL"}, "INVALID": {"INELIGIBLE"},
                           "UNRESOLVED": {"UNRESOLVED"}}
                if not isinstance(status, str) or status not in allowed.get(score["hard_gate_status"], set()):
                    raise HBQError(f"Saved scorer status conflicts with its control gate: {source}")
                item["scorer_status"] = status
        output.append(item)
    return {"readiness_view_version": 1, "report_sha256": hashlib.sha256(report_bytes).hexdigest(),
            "provenance": "local saved files; hashes identify bytes and do not authenticate origin",
            "scopes": output}
