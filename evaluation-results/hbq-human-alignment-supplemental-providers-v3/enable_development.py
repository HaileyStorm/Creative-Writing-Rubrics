#!/usr/bin/env python3
"""Create immutable batch-8 development permission only after a verified v3 pilot."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from study import CONTRACT, fingerprint, immutable_json, load_frozen, sha
from verify_transport_pilot import verify_pilot


def enable(work: Path) -> dict:
    load_frozen(work); pilot = verify_pilot(work)
    journal = [{"path": path.relative_to(work).as_posix(), **fingerprint(path)} for path in sorted((work / "pilot-journal").glob("[0-9][0-9][0-9][0-9]-*.json"))]
    value = {"format_version": 1, "study_id": CONTRACT["study_id"], "kind": "development_enablement", "contract_sha256": sha(Path(__file__).resolve().parent / "study-contract.json"), "frozen_contract_sha256": sha(work / "frozen-transport-contract.json"), "pilot": pilot, "pilot_claim": fingerprint(work / "pilot-execution-claim.json"), "pilot_verifier": fingerprint(Path(__file__).resolve().parent / "verify_transport_pilot.py"), "study": fingerprint(Path(__file__).resolve().parent / "study.py"), "development_enabler": fingerprint(Path(__file__)), "pilot_journal": journal, "development": CONTRACT["development"], "notice": "Batch-8 development is unmatched to primary batch-32 and v2 batch-16. The v2 failure does not promote Nous Pro; v3 failure has no automatic successor."}
    immutable_json(work / "development-enablement.json", value)
    return value


if __name__ == "__main__":
    parser = argparse.ArgumentParser(); parser.add_argument("--work-dir", type=Path, required=True)
    print(json.dumps(enable(parser.parse_args().work_dir.resolve()), sort_keys=True))
