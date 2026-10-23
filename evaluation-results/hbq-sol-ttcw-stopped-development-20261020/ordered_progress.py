"""Provider-free explicit-ID progress adapter for the prepared TTCW order.

The owning caller must serialize this run directory and reconcile other attempt
roots before use. This adapter is not a provider launcher, account/reservation
gate, semantic validator or replacement for the existing durable work queue.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from uuid import UUID, uuid4

from completion_order import PINS, encoded, require, sha


PLAN_SHA = "bd5ed49971f12538f8cbc691f8abd972847774be1fb95b948c2b902e7621e62d"


def create(path, value):
    with path.open("xb") as stream:
        stream.write(encoded(value))
        stream.flush()
        os.fsync(stream.fileno())


class OrderedProgress:
    def __init__(self, plan_path, manifest_path, census_path, root, purpose="offline_rehearsal"):
        require(purpose in {"offline_rehearsal", "collector_progress"}, "Unknown progress purpose")
        self.purpose = purpose
        plan_bytes = plan_path.read_bytes()
        manifest_bytes = manifest_path.read_bytes()
        census_bytes = census_path.read_bytes()
        require(sha(plan_bytes) == PLAN_SHA, "Prepared plan changed")
        require(sha(manifest_bytes) == PINS["manifest"] and sha(census_bytes) == PINS["census"], "Parent input changed")
        self.plan = json.loads(plan_bytes)
        self.rows = {row["ordinal"]: row for row in json.loads(manifest_bytes)["requests"]}
        census = json.loads(census_bytes)
        self.accepted_parent = {cell["ordinal"] for cell in census if cell["state"] == "accepted_saved_prediction"}
        self.occupied_parent = {cell["ordinal"] for cell in census if cell["state"] == "occupied_unadmitted_no_resend"}
        self.entries = self.plan["entries"]
        require(sha(encoded(self.plan["execution_condition"])) == self.plan["execution_condition_sha256"], "Execution condition changed")
        require({entry["source_ordinal"] for entry in self.entries} == set(range(334, 1045)) and len(self.entries) == 711, "Planned identities differ")
        for sequence, entry in enumerate(self.entries, 1):
            row = self.rows[entry["source_ordinal"]]
            require(entry["sequence"] == sequence and sha(encoded(row)) == entry["frozen_row_sha256"], "Frozen row binding differs")
            require(all(entry[key] == row[key] for key in ("logical_sample_id", "request_sha256")), "Request identity differs")
        self.root = root
        self.binding_base = {"schema_version": 1, "policy": "explicit_request_progress_v1", "plan_sha256": PLAN_SHA,
                        "execution_condition_sha256": self.plan["execution_condition_sha256"],
                        "manifest_sha256": PINS["manifest"], "census_sha256": PINS["census"],
                        "purpose": purpose, "provider_contact_authority": False}

    def sample(self, entry):
        return self.root / "samples" / ("%04d-%04d-%s" % (entry["sequence"], entry["source_ordinal"], entry["logical_sample_id"][:12]))

    def binding(self):
        record = json.loads((self.root / "binding.json").read_bytes())
        require(set(record) == set(self.binding_base) | {"run_id"}, "Run binding fields differ")
        require(all(record[key] == value for key, value in self.binding_base.items()), "Run binding differs")
        require(isinstance(record["run_id"], str), "Run identity must be a string")
        require(str(UUID(record["run_id"])) == record["run_id"], "Run identity malformed")
        return record

    def marker(self, entry, binding):
        return {"state": "before_contact", "progress_binding": {"run": binding, "entry": entry},
                "no_resend": True, "provider_contact_authority": False}

    def initialize(self):
        self.root.mkdir()
        create(self.root / "binding.json", {**self.binding_base, "run_id": str(uuid4())})
        (self.root / "samples").mkdir()

    def inspect(self):
        binding = self.binding()
        expected = {self.sample(entry).name: entry for entry in self.entries}
        attempted = set()
        accepted = set()
        rejected = set()
        unresolved = set()
        stopped = set()
        for path in (self.root / "samples").iterdir():
            require(path.name in expected and path.is_dir() and not path.is_symlink(), "Unknown occupied sample; reconcile before continuing")
            entry = expected[path.name]
            n = entry["source_ordinal"]
            attempted.add(n)
            marker_bytes = (path / "attempt-started.json").read_bytes()
            marker = self.marker(entry, binding)
            require(json.loads(marker_bytes) == marker, "Missing or changed attempt marker; no retry")
            terminal = path / "terminal.json"
            if not terminal.exists():
                unresolved.add(n)
                continue
            result = json.loads(terminal.read_bytes())
            require(result.get("no_resend") is True, "Terminal lacks no-resend binding")
            require(result.get("progress_binding") == marker["progress_binding"], "Terminal request/run binding differs")
            require(result.get("attempt_marker_sha256") == sha(marker_bytes), "Terminal attempt binding differs")
            state = result.get("state")
            require(state in {"accepted", "semantic_rejected", "unadmitted_no_resend"}, "Unknown terminal state")
            if state == "unadmitted_no_resend":
                stopped.add(n)
                continue
            require(result.get("accepted") is (state == "accepted"), "Terminal acceptance differs")
            for field, name in (("native_result_sha256", "native-result.json"), ("response_sha256", "response.json"), ("acceptance_sha256", "acceptance.json")):
                require(sha((path / name).read_bytes()) == result.get(field), "Terminal artifact commitment differs")
            admission = json.loads((path / "acceptance.json").read_bytes())
            require(admission.get("accepted") is (state == "accepted"), "Admission and terminal disagree")
            (accepted if state == "accepted" else rejected).add(n)
        remaining = [entry for entry in self.entries if entry["source_ordinal"] not in attempted]
        held = bool(unresolved or stopped)
        return {"policy": "explicit_request_progress_v1", "plan_sha256": PLAN_SHA, "purpose": self.purpose,
                "parent_accepted_ordinals": sorted(self.accepted_parent), "parent_occupied_no_resend_ordinals": sorted(self.occupied_parent),
                "attempted_ordinals": sorted(attempted), "accepted_ordinals": sorted(accepted),
                "semantic_rejected_ordinals": sorted(rejected), "unresolved_ordinals": sorted(unresolved),
                "stopped_no_resend_ordinals": sorted(stopped),
                "remaining_unattempted_ordinals": [entry["source_ordinal"] for entry in remaining],
                "state": "HELD_FOR_RECONCILIATION" if held else "EXHAUSTED" if not remaining else "NEXT_ID_IDENTIFIED_NO_CONTACT_AUTHORITY",
                "next_entry": None if held or not remaining else remaining[0], "provider_contact_authority": False,
                "acceptance_meaning": "Hash-bound producer admission receipt; this inspection does not revalidate native controls, quotations or semantic correctness."}

    def reserve_next(self):
        status = self.inspect()
        entry = status["next_entry"]
        require(entry is not None, "No dispatchable identity; reconcile held attempts without resend")
        path = self.sample(entry)
        # Directory occupancy itself fences an interruption before marker completion.
        path.mkdir()
        marker = self.marker(entry, self.binding())
        create(path / "attempt-started.json", marker)
        return {"entry": entry, "sample_path": str(path), "frozen_request": self.rows[entry["source_ordinal"]],
                "terminal_binding": {"progress_binding": marker["progress_binding"],
                                     "attempt_marker_sha256": sha((path / "attempt-started.json").read_bytes())},
                "provider_contact_authority": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("init", "status", "reserve"))
    for name in ("plan", "manifest", "census", "run-dir"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--purpose", choices=("offline_rehearsal", "collector_progress"), default="offline_rehearsal")
    args = parser.parse_args()
    try:
        progress = OrderedProgress(args.plan, args.manifest, args.census, args.run_dir, args.purpose)
        if args.action == "init":
            progress.initialize()
        if args.action == "reserve":
            result = progress.reserve_next()
            # Keep payload and private operational paths out of the console summary.
            output = {"entry": result["entry"], "provider_contact_authority": False}
        else:
            output = progress.inspect()
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.exit(2, f"ordered progress: {error}\n")
    print(json.dumps(output, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
