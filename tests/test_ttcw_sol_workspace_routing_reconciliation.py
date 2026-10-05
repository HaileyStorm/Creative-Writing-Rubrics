"""Synthetic named routing-recipient witnesses; no provider/runtime proof."""
from copy import deepcopy
from datetime import datetime, timedelta
import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
HERE = REPO / "evaluation-results/hbq-matched-ttcw-20261004"
import importlib.util


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


old = load("routing_reused_fixture", REPO / "tests/test_ttcw_sol_transport_reconciliation.py")
m = load("routing_recipient_test", HERE / "reconcile_sol_workspace_routing.py")


@pytest.fixture
def case(tmp_path, monkeypatch):
    original = old.case.__wrapped__(tmp_path, monkeypatch)
    before = original["sample"].resolve()
    sample = original["results"] / m.SLOT
    assert before.is_relative_to(tmp_path.resolve()) and sample.resolve().is_relative_to(tmp_path.resolve())
    before.rename(sample)
    original["sample"] = sample
    monkeypatch.setattr(m, "HOME", original["home"])
    row = deepcopy(original["row"])
    row["endpoint_ordinal"] = 392
    row["logical_sample_id"] = "be39ffd1004a" + "a" * 52
    row.pop("request_sha256")
    row["request_sha256"] = m.digest(m.canonical(row))
    manifest_path = original["frozen"] / "manifest.json"
    manifest = json.loads(manifest_path.read_bytes()); manifest["requests"] = [row]
    manifest_raw = m.canonical(manifest); manifest_path.write_bytes(manifest_raw)
    job_path = original["results"] / "job.json"
    job = json.loads(job_path.read_bytes()); job["manifest_sha256"] = m.digest(manifest_raw)
    job_path.write_bytes(m.canonical(job))
    final = (sample / "responses/batch-0001.attempt-0001.message.json").read_bytes()
    native, events, _ = old.f.native_fixture(sample, original["artifacts"]["prompt.txt"].decode(), final.decode())
    diagnostics = [{"type": "error", "message": f"Reconnecting... {n}/5 (workspace routing discovery failed)"} for n in (2, 3, 4, 5)]
    diagnostics.append({"type": "item.completed", "item": {"id": "fallback", "type": "error",
        "message": "Falling back from WebSockets to HTTPS transport. workspace routing discovery failed"}})
    diagnostics += [{"type": "error", "message": f"Reconnecting... {n}/5 (workspace routing discovery failed)"} for n in (1, 2, 3, 4, 5)]
    events[3:3] = diagnostics
    started = {"time": "2026-10-05T01:01:38Z", "session_id": None, "state": "before_contact", "no_resend": True}
    native[0]["timestamp"] = (datetime.fromisoformat(started["time"].replace("Z", "+00:00")) + timedelta(seconds=3343.324667)).isoformat()
    native[-1]["timestamp"] = "2026-10-05T01:58:28Z"
    original["rollout"].write_bytes(old.f.raw(native))
    stem = sample / "responses/batch-0001.attempt-0001"
    terminal = {"state": "unadmitted_no_resend", "accepted": False, "no_resend": True,
        "error_class": "_ProviderAttemptFailure", "error": "timeout after 300 seconds", "provider_record": {
        "provider_artifacts": {"codex_events": {"path": "responses/batch-0001.attempt-0001.events.jsonl",
            "sha256": m.digest(old.f.raw(events)), "bytes": len(old.f.raw(events))}}}}
    files = {"manifest": (manifest_path, manifest_raw), "job": (job_path, m.canonical(job)),
        "condition": (sample / "condition.json", m.canonical(row)), "started": (sample / "attempt-started.json", m.canonical(started)),
        "identity": (sample / "native-identity.json", m.canonical({"logical_sample_id": row["logical_sample_id"], "session_id": None})),
        "terminal": (sample / "terminal.json", m.canonical(terminal)), "events": (Path(str(stem) + ".events.jsonl"), old.f.raw(events)),
        "final": (Path(str(stem) + ".message.json"), final), "rollout": (original["rollout"], old.f.raw(native))}
    for path, raw in files.values(): path.write_bytes(raw)
    monkeypatch.setattr(m, "PINNED", {name: (m.digest(raw), len(raw)) for name, (_, raw) in files.items()})
    monkeypatch.setattr(m, "PROJECTION_SHA", m.digest(m.routing_projection(old.f.raw(events), original["transport"].codex_receipts)[0]))
    original.update(row=row, files=files, events=events)
    return original


def reconcile(case, **kwargs):
    return m.reconcile(case["frozen"] / "manifest.json", case["results"], m.SLOT, case["home"], case["rollout"], **kwargs)


def snapshot(case, output):
    saved, response, acceptance, reads = reconcile(case)
    output.mkdir()
    for name, raw in reads.raws.items():
        path = output / saved["source_commitments"][name]["snapshot"]
        path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(raw)
    (output / "reconciliation.json").write_bytes(m.canonical(saved))
    (output / "response.json").write_bytes(response)
    (output / "acceptance.json").write_bytes(m.canonical(acceptance))
    (output / "terminal.json").write_bytes(m.canonical({"state": saved["state"], "no_resend": True,
        "reconciliation_sha256": m.digest(m.canonical(saved))}))
    return saved


def test_routing_snapshot_retains_original_timeout_gap_and_raw_final(case, tmp_path):
    output = tmp_path / "descendant"
    saved = snapshot(case, output)
    assert saved["accepted"] and not saved["abstention"]
    assert saved["new_logical_votes"] == saved["provider_calls_made"] == 0
    assert saved["native"]["unexplained_native_start_gap_seconds"] == 3343.324667
    assert saved["native"]["original_terminal_events_equal_retained"] and not saved["native"]["late_append_demonstrated"]
    assert not saved["native"]["original_receipt_policy_satisfied"] and not saved["native"]["generic_saved_transport_policy_satisfied"]
    original_terminal, raw_final = case["files"]["terminal"][1], case["files"]["final"][1]
    for path, _ in case["files"].values(): path.unlink()
    actual, final, _, reads = reconcile(case, snapshot=output, commitments=saved["source_commitments"])
    assert actual == saved and final == raw_final and reads.raws["terminal"] == original_terminal


@pytest.mark.parametrize("damage", ["unknown_error", "order", "extra_error", "error_fields", "late", "foreign", "fallback"])
def test_only_exact_observed_routing_diagnostics_are_projected(case, damage):
    events = deepcopy(case["events"])
    if damage == "unknown_error": events[3]["message"] = "Reconnecting... 2/5 (Authentication failed)"
    elif damage == "order": events[3], events[4] = events[4], events[3]
    elif damage == "extra_error": events.insert(4, deepcopy(events[3]))
    elif damage == "error_fields": events[3]["extra"] = True
    elif damage == "late": events.append(events.pop(3))
    elif damage == "foreign": events[3]["thread_id"] = old.f.FOREIGN
    else: events[7]["item"]["message"] += " Other failure."
    with pytest.raises(ValueError): m.routing_projection(old.f.raw(events), case["transport"].codex_receipts)
    with pytest.raises(ValueError, match="Unknown native transport error"):
        case["transport"].sol_projection(old.f.raw(case["events"]))


@pytest.mark.parametrize("damage", ["tool", "incomplete", "prompt", "session", "cwd", "final"])
def test_unchanged_native_reader_rejects_unbound_completed_evidence(case, damage):
    events = deepcopy(case["events"])
    native = [json.loads(line) for line in case["rollout"].read_bytes().splitlines()]
    final = case["files"]["final"][1]
    if damage == "tool": events.insert(-1, {"type": "item.completed", "item": {"type": "command_execution"}})
    elif damage == "incomplete": native.pop()
    elif damage == "prompt": native[6]["payload"]["content"][0]["text"] = "Changed prompt."
    elif damage == "session": native[0]["payload"]["id"] = old.f.FOREIGN
    elif damage == "cwd": native[0]["payload"]["cwd"] = str(case["results"] / "other-slot")
    else: final += b"{}"
    projection, _ = m.routing_projection(old.f.raw(events), case["transport"].codex_receipts)
    with pytest.raises(ValueError):
        case["transport"].codex_receipts.project(old.f.raw(native), projection, final,
            prompt=case["artifacts"]["prompt.txt"].decode(), model="gpt-6.1-sol", reasoning="high", cwd=case["sample"])


@pytest.mark.parametrize("damage", ["source", "condition", "missing_pin", "projection"])
def test_pins_and_private_snapshots_fail_closed(case, tmp_path, damage):
    output = tmp_path / "descendant"; saved = snapshot(case, output)
    if damage == "source":
        (case["frozen"] / "source.txt").write_bytes(b"Changed source.")
        with pytest.raises(ValueError, match="Frozen artifact"): reconcile(case)
    elif damage == "condition":
        case["files"]["condition"][0].write_bytes(b"{}")
        with pytest.raises(ValueError, match="Pinned source"): reconcile(case)
    else:
        pins = deepcopy(saved["source_commitments"])
        if damage == "missing_pin": pins.pop("condition")
        else: (output / pins["events_projection"]["snapshot"]).write_bytes(b"Different projection\n")
        with pytest.raises(ValueError, match="Snapshot|snapshot"):
            reconcile(case, snapshot=output, commitments=pins)


def test_same_failed_record_joined_once_without_label_release(case, tmp_path):
    output = tmp_path / "descendant"; saved = snapshot(case, output)
    chain = old.a; loaded = chain.modules(); loaded["reconcile_sol_workspace_routing"] = m
    row = case["row"]; identity = ("sol", row["logical_sample_id"])
    record = {"request": row, "state": "unadmitted_no_resend", "accepted": None,
              "terminal_sha256": m.PINNED["terminal"][0], "source_index": 0}
    joined = {identity: record, ("grok", "untouched"): {"state": "not_collected"}}
    source = {"endpoint": "sol", "manifest_path": str(case["frozen"] / "manifest.json"),
        "manifest_sha256": m.PINNED["manifest"][0], "job_sha256": m.PINNED["job"][0], "results_root": str(case["results"])}
    spec = {"path": str(output / "reconciliation.json"), "sha256": m.digest(m.canonical(saved))}
    with pytest.raises(ValueError, match="source lineage"):
        chain.apply_reconciliation(spec, joined, [dict(source, job_sha256="wrong-source")], case["artifacts"], loaded, None)
    chain.apply_reconciliation(spec, joined, [source], case["artifacts"], loaded, None)
    assert len(joined) == 2 and record["state"] == "accepted" and record["original_state"] == "unadmitted_no_resend"
    with pytest.raises(ValueError, match="one original failed slot"):
        chain.apply_reconciliation(spec, joined, [source], case["artifacts"], loaded, None)
    with pytest.raises(ValueError, match="every original planned"): chain.label_release_gate(joined, expected=2)


def test_wrong_slot_output_or_account_cannot_reuse_saved_observation(case, tmp_path):
    with pytest.raises(ValueError, match="no resend"):
        m.reconcile(case["frozen"] / "manifest.json", case["results"], old.m.SLOT, case["home"], case["rollout"])
    with pytest.raises(ValueError, match="account/session"):
        m.reconcile(case["frozen"] / "manifest.json", case["results"], m.SLOT, tmp_path / "other-account", case["rollout"])
    with pytest.raises(ValueError): m.base.fresh_output(case["sample"] / "descendant", [case["results"]])


def test_canonical_final_parser_rejects_duplicate_documents_keys_and_nonfinite():
    for raw in (b'{}{}', b'{"a":1,"a":2}', b'{"a":NaN}'):
        with pytest.raises(ValueError): m.unique_json(raw)


def test_completed_native_final_still_requires_frozen_quote_validation(case, monkeypatch):
    final_path = case["files"]["final"][0]
    response = json.loads(final_path.read_bytes())
    response["result"]["dimensions"][0]["evidence"][0]["quote"] = "Quotation absent from source."
    final = m.canonical(response)
    events = deepcopy(case["events"]); events[-2]["item"]["text"] = final.decode()
    native = [json.loads(line) for line in case["rollout"].read_bytes().splitlines()]
    native[8]["payload"]["content"][0]["text"] = final.decode()
    native[-1]["payload"]["last_agent_message"] = final.decode()
    final_path.write_bytes(final); case["rollout"].write_bytes(old.f.raw(native))
    case["files"]["events"][0].write_bytes(old.f.raw(events))
    terminal_path = case["files"]["terminal"][0]
    terminal = json.loads(terminal_path.read_bytes())
    terminal["provider_record"]["provider_artifacts"]["codex_events"].update(
        sha256=m.digest(old.f.raw(events)), bytes=len(old.f.raw(events)))
    terminal_path.write_bytes(m.canonical(terminal))
    for name in ("final", "rollout", "events", "terminal"):
        raw = case["files"][name][0].read_bytes(); m.PINNED[name] = (m.digest(raw), len(raw))
    monkeypatch.setattr(m, "PROJECTION_SHA", m.digest(m.routing_projection(old.f.raw(events), case["transport"].codex_receipts)[0]))
    saved, _, acceptance, _ = reconcile(case)
    assert not acceptance["accepted"] and "substring" in acceptance["errors"][0]
    assert saved["state"] == "completed_semantically_rejected" and saved["no_resend"]
