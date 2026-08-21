#!/usr/bin/env python3
"""Freeze the batch-16 development permission only after the transport pilot passes."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from study import CONTRACT, fingerprint, immutable_json, load_frozen, sha
from verify_transport_pilot import verify_pilot


def _journal_binding(work: Path) -> list[dict]:
    root = work / "pilot-journal"
    return [{"path": path.relative_to(work).as_posix(), **fingerprint(path)} for path in sorted(root.glob("[0-9][0-9][0-9][0-9]-*.json"))]


def enable(work: Path) -> dict:
    frozen = load_frozen(work)
    pilot = verify_pilot(work)
    value = {
        "format_version": 1,
        "study_id": CONTRACT["study_id"],
        "kind": "development_enablement",
        "contract_sha256": sha(Path(__file__).resolve().parent / "study-contract.json"),
        "frozen_contract_sha256": sha(work / "frozen-transport-contract.json"),
        "pilot": pilot,
        "pilot_claim": fingerprint(work / "pilot-execution-claim.json"),
        "pilot_verifier": fingerprint(Path(__file__).resolve().parent / "verify_transport_pilot.py"),
        "study": fingerprint(Path(__file__).resolve().parent / "study.py"),
        "development_enabler": fingerprint(Path(__file__)),
        "pilot_journal": _journal_binding(work),
        "development": CONTRACT["development"],
        "notice": "The v1 transport failure does not promote Nous Pro. Development is batch-16 and any comparison is unmatched to primary batch-32 unless paired Sol-16 cells are separately frozen.",
    }
    immutable_json(work / "development-enablement.json", value)
    return value


def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("--work-dir", type=Path, required=True)
    print(json.dumps(enable(parser.parse_args().work_dir.resolve()), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
