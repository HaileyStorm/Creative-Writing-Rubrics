"""Pinned Sol392 exploratory recipient projection; no provider calls or resends.

The original300-second failure and unexplained native-start gap remain evidence.
This policy grants neither original strict admission nor contact/runtime claims.
"""
from __future__ import annotations

import argparse
from datetime import timedelta
import hashlib
import importlib.util
import json
from pathlib import Path
import re

HERE = Path(__file__).resolve().parent
BASE_SHA = "7994fa6c0cfe74120f5c8e5add077943662f3935e6a6a3d8129a6f71a40bf8cb"
base_path = HERE / "reconcile_sol_transport.py"
if hashlib.sha256(base_path.read_bytes()).hexdigest() != BASE_SHA:
    raise ValueError("Pinned Sol391 wrapper differs")
spec = importlib.util.spec_from_file_location("ttcw_routing_base", base_path)
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)
REPO, HOME = base.REPO, base.HOME
canonical, digest, require = base.canonical, base.digest, base.require
POLICY = "ttcw_saved_sol_workspace_routing_reconciliation_v1"
SLOT = "0392-be39ffd1004a"
PROJECTION_SHA = "4061cd469149f5771662b48e362caeb85850d23f3f3a6aa3330f6cbbe6239ed5"
EXPECTED_SEQUENCE = [("reconnect", n) for n in (2, 3, 4, 5)] + [("fallback", None)] + [("reconnect", n) for n in (1, 2, 3, 4, 5)]
PINNED = {
    "manifest": ("d5cc19e50360c5d12e8aa118df5f8e89840174cb308964034be9d6873f500914", 2481729),
    "job": ("bffcfc94a36b028b9ac2ea9651fb16150357a7933f351e3fa21120588ede0676", 1119),
    "condition": ("dc76173ec81a2aabc81cf9b14b73b27dee3ddf7963457cd7184681c0723dbf33", 1188),
    "started": ("43eb1e4182192aa44481e21ffd642b105194d743e15d914a813eeb94470109bb", 121),
    "identity": ("8fe15a6f1003cf307f78ba2e827f64ce0890ef2816dbe0781629a252156231cd", 116),
    "terminal": ("e796531894ec04c6ae4754eddbea8e21424aeb1aef2ab4013bb4a1e17616d6c8", 2013),
    "events": ("48117d8cf25cfcb3fbe111f8f788811ad94cc83d6af4036f87343d663c313423", 3732),
    "final": ("a610a059783e12180bd6c2f1a45bd57c71894e47acdb6bc126dee0f5610f4bc8", 2117),
    "rollout": ("0d76a61462e0ab07c177e4ce815775dcfcc1c0cbb4c56454929c2470ee482501", 71741),
}


def routing_projection(events, reader):
    rows = reader._rows(events)
    require(rows[0][1].get("type") == "thread.started", "Missing own native thread")
    thread = reader._uuid(rows[0][1].get("thread_id"))
    kept, diagnostics, sequence = [], [], []
    started = finished = False
    for line, event in rows:
        require(event.get("thread_id", thread) == thread, "Routing diagnostic has foreign thread")
        kind, item = event.get("type"), event.get("item", {})
        diagnostic = kind == "error" or (kind == "item.completed" and item.get("type") == "error"
                     and item.get("message") != reader.STARTUP_DIAGNOSTIC)
        if diagnostic:
            require(started and not finished, "Routing diagnostic outside own turn")
            if kind == "error":
                require(set(event) == {"type", "message"}, "Unknown routing error fields")
                message = event["message"]
                match = re.fullmatch(r"Reconnecting\.\.\. ([1-5])/5 \(workspace routing discovery failed\)", message)
                require(match is not None, "Unknown routing error")
                sequence.append(("reconnect", int(match[1])))
            else:
                message = item.get("message")
                require(set(event) == {"type", "item"} and set(item) == {"id", "type", "message"}
                        and message == "Falling back from WebSockets to HTTPS transport. workspace routing discovery failed",
                        "Unknown routing diagnostic")
                sequence.append(("fallback", None))
            diagnostics.append({"line_sha256": digest(line), "type": kind, "message": message})
            continue
        kept.append(line)
        started = started or kind == "turn.started"
        finished = finished or kind == "turn.completed"
    require(sequence == EXPECTED_SEQUENCE, "Observed routing diagnostic sequence differs")
    return b"\n".join(kept) + b"\n", diagnostics


def unique_json(raw):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, "Duplicate saved final key")
            result[key] = value
        return result
    def nonfinite(value):
        raise ValueError("Nonfinite saved final number")
    return json.loads(raw, object_pairs_hook=unique, parse_constant=nonfinite)


def reconcile(manifest_path, results, slot, home, rollout, *, snapshot=None, commitments=None):
    require(slot == SLOT, "Only pinned Sol392 is supported; no resend")
    require(home.resolve() == HOME.resolve() and rollout.resolve().is_relative_to(home.resolve() / "sessions"),
            "Selected own account/session root differs")
    transport_path = REPO / "evaluation-results/hbq-native-transport-recovery-v1/reconcile.py"
    reader_path = REPO / "src/hbqrs/codex_receipts.py"
    require(digest(base_path.read_bytes()) == BASE_SHA and digest(transport_path.read_bytes()) == base.TRANSPORT_SHA
            and digest(reader_path.read_bytes()) == base.READER_SHA, "Pinned recovery implementation differs")
    transport = base.load("ttcw392_unchanged_transport", transport_path)
    reader = transport.codex_receipts
    class Reads(transport.ReadSet):
        def raw(self, name, path):
            require(self.snapshot is None or name in self.expected, "Snapshot source commitment missing: " + name)
            raw = super().raw(name, path)
            if name in PINNED:
                require((digest(raw), len(raw)) == PINNED[name], "Pinned source differs: " + name)
            return raw
    reads = Reads(snapshot=snapshot, commitments=commitments)
    sample = results / slot
    paths = {"manifest": manifest_path, "job": results / "job.json", "condition": sample / "condition.json",
        "started": sample / "attempt-started.json", "identity": sample / "native-identity.json", "terminal": sample / "terminal.json"}
    values = {name: json.loads(reads.raw(name, path)) for name, path in paths.items()}
    manifest, job, row = values["manifest"], values["job"], values["condition"]
    require(row["endpoint"] == "sol" and row["endpoint_ordinal"] == 392 and row in manifest["requests"]
            and f"0392-{row['logical_sample_id'][:12]}" == slot
            and digest(canonical({k: v for k, v in row.items() if k != "request_sha256"})) == row["request_sha256"],
            "Original frozen condition differs")
    require(job["manifest_sha256"] == digest(reads.raws["manifest"]) and job["endpoint"] == "sol"
            and job["model"] == "gpt-6.1-sol" and job["reasoning"] == "high" and job["automatic_retries"] == 0
            and job["zero_charge_only"] is True and job["receipt_reader_sha256"] == base.READER_SHA
            and job["validator_sha256"] == base.VALIDATOR_SHA
            and job["account_identity_sha256"] == "4392760f900d3f082618c27721f07cbc9ffca06b91bb9ac8fa5f20695625d2de"
            and job["helper_sha256"] == "c0a3563dab36105830c9e63be7fdeb551ef7a9805a5b5b44450c9e6501be3b01",
            "Original job/account/runtime differs")
    started, terminal = values["started"], values["terminal"]
    require(values["identity"] == {"logical_sample_id": row["logical_sample_id"], "session_id": None}
            and started["session_id"] is None and started["state"] == "before_contact" and started["no_resend"] is True,
            "Original own identity/start differs")
    require(terminal["accepted"] is False and terminal["state"] == "unadmitted_no_resend" and terminal["no_resend"] is True
            and terminal["error_class"] == "_ProviderAttemptFailure" and "300 seconds" in terminal["error"],
            "Original300-second timeout differs")
    stem = sample / "responses/batch-0001.attempt-0001"
    events = reads.raw("events", Path(str(stem) + ".events.jsonl"))
    final = reads.raw("final", Path(str(stem) + ".message.json"))
    require(terminal["provider_record"]["provider_artifacts"]["codex_events"] == {
        "path": "responses/batch-0001.attempt-0001.events.jsonl", "sha256": digest(events), "bytes": len(events)},
        "Original terminal/current events equality differs")
    artifacts = {}
    names = {"context.txt", row["prompt_path"], row["schema_path"], *(s["input_path"] for s in row["sources"])}
    for index, name in enumerate(sorted(names)):
        relative = Path(name)
        require(not relative.is_absolute() and ".." not in relative.parts, "Frozen path escapes manifest")
        raw = reads.raw("frozen_" + str(index), manifest_path.parent / name)
        pin = manifest["artifacts"][name]
        require((digest(raw), len(raw)) == (pin["sha256"], pin["bytes"]), "Frozen artifact pin differs")
        artifacts[name] = raw
    for kind in ("prompt", "schema"):
        raw = artifacts[row[kind + "_path"]]
        require((digest(raw), len(raw)) == (row[kind + "_sha256"], row[kind + "_bytes"]), "Frozen request bytes differ")
    for source in row["sources"]:
        require(digest(artifacts[source["input_path"]]) == source["sha256"], "Frozen source differs")
    require(reads.raw("attempt_schema", sample / "schema.json") == artifacts[row["schema_path"]], "Attempt schema differs")
    for name, path, expected in (("sol391_implementation", base_path, BASE_SHA),
        ("transport_implementation", transport_path, base.TRANSPORT_SHA), ("reader_implementation", reader_path, base.READER_SHA),
        ("validator_implementation", HERE / "validate_response.py", base.VALIDATOR_SHA),
        ("schema_implementation", base.TOOLS / "model_work_queue/adapters/json_schema_subset.py", manifest["implementation"]["schema_subset_sha256"])):
        require(digest(reads.raw(name, path)) == expected, "Frozen admission implementation differs")
    require(manifest["implementation"]["semantic_validator_sha256"] == base.VALIDATOR_SHA, "Frozen semantic validator differs")
    projection, diagnostics = routing_projection(events, reader)
    require(digest(projection) == PROJECTION_SHA, "Pinned routing projection differs")
    reads.raws["events_projection"], reads.paths["events_projection"] = projection, "derived:exact_observed_workspace_routing_projection"
    if snapshot is not None:
        require(reads.raw("events_projection", Path(reads.paths["events_projection"])) == projection, "Snapshot derived events differ")
    own = reads.raw("rollout", rollout)
    receipt = reader.project(own, projection, final, prompt=artifacts[row["prompt_path"]].decode(),
                            model=job["model"], reasoning=job["reasoning"], cwd=sample)
    records = [event for _, event in reader._rows(own)]
    completed = [event for event in records if event.get("type") == "event_msg" and event["payload"].get("type") == "task_complete"]
    require(len(completed) == 1, "Own saved turn completion differs")
    native_start, native_end, attempted = (transport.timestamp(value) for value in
        (records[0]["timestamp"], completed[0]["timestamp"], started["time"]))
    require(attempted - timedelta(seconds=120) <= native_start <= native_end, "Own native time order differs")
    gap = (native_start - attempted).total_seconds()
    require(gap == 3343.324667, "Pinned unexplained native-start gap differs")
    response = unique_json(final)
    subset = base.load("ttcw392_subset", base.TOOLS / "model_work_queue/adapters/json_schema_subset.py")
    validator = base.load("ttcw392_validator", HERE / "validate_response.py")
    acceptance = validator.semantic_validate(row["arm"], response, row,
        {s["id"]: artifacts[s["input_path"]].decode() for s in row["sources"]}, subset,
        context=artifacts["context.txt"].decode(), schema=json.loads(artifacts[row["schema_path"]]))
    native = {"policy": POLICY, "native_reader_receipt": receipt, "diagnostics": diagnostics,
        "raw_events_sha256": digest(events), "filtered_events_sha256": digest(projection),
        "original_receipt_policy_satisfied": False, "generic_saved_transport_policy_satisfied": False,
        "physical_contact_cardinality_proven": False, "original_terminal_events_equal_retained": True,
        "late_append_demonstrated": False, "unexplained_native_start_gap_seconds": gap,
        "original_started_time": started["time"], "native_started_time": records[0]["timestamp"],
        "native_completed_time": completed[0]["timestamp"]}
    saved = {"policy": POLICY, "evidence_class": POLICY, "endpoint": "sol", "slot": slot, "endpoint_ordinal": 392,
        "logical_sample_id": row["logical_sample_id"], "request_sha256": row["request_sha256"],
        "state": "completed_semantically_accepted" if acceptance["accepted"] else "completed_semantically_rejected",
        "accepted": acceptance["accepted"], "abstention": acceptance["abstention"], "semantic_errors": acceptance["errors"],
        "original_terminal_preserved": "unadmitted_no_resend", "original_timeout_seconds": 300,
        "no_resend": True, "provider_calls_made": 0, "new_logical_votes": 0, "full_planned_denominator": 3108,
        "human_labels_released": False, "original_native_envelope_reconstructed": False, "full_runtime_contract_attested": False,
        "native": native, "source_commitments": reads.commitments(), "response_sha256": digest(final),
        "canonical_response_sha256": digest(canonical(response)), "acceptance_sha256": digest(canonical(acceptance)),
        "implementation_sha256": digest(Path(__file__).read_bytes())}
    return saved, final, acceptance, reads


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("manifest", "results-root", "own-home", "rollout", "output-root"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--slot", default=SLOT)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    output = base.fresh_output(args.output_root, [REPO, args.manifest.parent, args.results_root, args.own_home, args.rollout.parent])
    saved, response, acceptance, reads = reconcile(args.manifest.resolve(), args.results_root.resolve(), args.slot,
                                                  args.own_home.resolve(), args.rollout.resolve())
    if not args.dry_run:
        output.mkdir(parents=True, exist_ok=False)
        base.write_new(output / "invocation.json", canonical(base.vars_for_receipt(args)))
        try:
            (output / "native").mkdir()
            for name, raw in reads.raws.items():
                if name != "events_projection":
                    require(Path(reads.paths[name]).read_bytes() == raw, "Source changed before snapshot")
                base.write_new(output / "native" / (name + ".bin"), raw)
            base.write_new(output / "reconcile_sol_workspace_routing.py", Path(__file__).read_bytes())
            base.write_new(output / "response.json", response)
            base.write_new(output / "acceptance.json", canonical(acceptance))
            base.write_new(output / "reconciliation.json", canonical(saved))
            base.write_new(output / "terminal.json", canonical({"state": saved["state"], "no_resend": True,
                           "reconciliation_sha256": digest(canonical(saved))}))
        except (OSError, ValueError):
            if not (output / "terminal.json").exists():
                base.write_new(output / "terminal.json", canonical({"state": "failed_private_snapshot_pending", "no_resend": True}))
            raise
    print(json.dumps({"policy": POLICY, "dry_run": args.dry_run, "accepted": saved["accepted"], "abstention": saved["abstention"],
        "semantic_error_count": len(saved["semantic_errors"]), "verified_input_files": len(reads.raws),
        "receipt_sha256": digest(canonical(saved)), "response_sha256": digest(response), "new_logical_votes": 0,
        "provider_calls_made": 0, "full_planned_denominator": 3108, "human_labels_released": False,
        "unexplained_native_start_gap_seconds": saved["native"]["unexplained_native_start_gap_seconds"]}, sort_keys=True))


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise SystemExit("Sol routing reconciliation pending: " + type(error).__name__) from None
