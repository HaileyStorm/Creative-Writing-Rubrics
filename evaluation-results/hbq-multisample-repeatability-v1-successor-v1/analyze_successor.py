"""Bounded lineage adapter for the 76 inherited and 254 successor schedule cells."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from run_successor import BINDING, EXECUTION, JOURNAL, _binding_path, _read_journal, _session_ids_in_output, _validate_normalization, _v1_runner
from study import bind_predecessor, canonical, plans, predecessor_session_ids, read_json, sha, write_immutable_json


def validate_combined(predecessor_root: Path, work: Path) -> dict[str, Any]:
    predecessor = bind_predecessor(predecessor_root)
    if read_json(work / BINDING) != predecessor:
        raise ValueError("Successor predecessor binding drifted")
    execution = read_json(work / EXECUTION)
    if execution.get("predecessor_binding_sha256") != hashlib.sha256(canonical(predecessor)).hexdigest():
        raise ValueError("Successor execution contract does not bind its predecessor")
    frozen = read_json(predecessor_root / "frozen-run-contract.json")
    all_plans, successor = plans(frozen), plans(frozen)[76:]
    records = _read_journal(work / JOURNAL)
    if len(records) != len(successor) * 2 or records[:len(successor)] != successor:
        raise ValueError("Successor schedule is incomplete or not the exact 254-cell continuation")
    completed = records[len(successor):]
    predecessor_sessions = set(predecessor_session_ids(predecessor_root))
    if len(predecessor_sessions) != predecessor["sessions"]["count"]:
        raise ValueError("Predecessor session binding cannot be replayed")
    sessions: set[str] = set()
    runner = None
    for event, record in zip(successor, completed):
        digest = record.get("run_binding_sha256")
        if record != {**event, "event": "completed", "run_binding_sha256": digest} or not isinstance(digest, str) or len(digest) != 64:
            raise ValueError("Successor completion record drifted")
        target = _binding_path(work, event)
        if not target.is_file() or sha(target) != digest:
            raise ValueError("Successor completion has no matching final artifact")
        normalization = [target.parent / name for name in ("raw-response.json", "raw-result.json", "normalization-audit.json", "normalization-marker.json")]
        pass_manifest = read_json(target)
        if "normalization_marker_sha256" in pass_manifest or any(path.exists() for path in normalization):
            source = predecessor_root / "inputs" / str(event["item_id"]) / "source.md"
            runner = runner or _v1_runner()
            _validate_normalization(runner, target.parent, source.read_text(encoding="utf-8"))
        for session in _session_ids_in_output(target.parent):
            if session in predecessor_sessions or session in sessions:
                raise ValueError("Successor session collides with predecessor or another successor output")
            sessions.add(session)
    inherited = predecessor["accepted_prefix"]
    combined = {
        "format_version": 1,
        "study_id": "hbq-multisample-repeatability-v1-successor-v1",
        "scope": "lineage_only; scoring uses the v1 analyzer after its raw-artifact replay contract is extended for explicit normalization projections",
        "predecessor_binding_sha256": hashlib.sha256(canonical(predecessor)).hexdigest(),
        "inherited": inherited,
        "successor": {"count": len(completed), "first_sequence": completed[0]["sequence"], "last_sequence": completed[-1]["sequence"], "session_count": len(sessions)},
        "combined": {"count": len(all_plans), "first_sequence": 1, "last_sequence": 330},
    }
    return combined


def analyze(predecessor_root: Path, work: Path, output: Path) -> dict[str, Any]:
    combined = validate_combined(predecessor_root, work)
    write_immutable_json(output / "combined-330-lineage.json", combined)
    return combined


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("predecessor_root", type=Path)
    parser.add_argument("work", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    print(json.dumps(analyze(args.predecessor_root.resolve(), args.work.resolve(), args.output.resolve()), sort_keys=True))


if __name__ == "__main__":
    main()
