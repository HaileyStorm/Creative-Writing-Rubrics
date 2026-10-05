"""Synthetic exact-source/native witnesses; these do not claim provider proof."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
HERE = REPO / "evaluation-results/hbq-matched-ttcw-20261004"


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


m = load("sol391_test_wrapper", HERE / "reconcile_sol_transport.py")
a = load("sol391_test_chain", HERE / "analysis_chain.py")
f = load("sol391_test_native", REPO / "tests/test_codex_receipts.py")


@pytest.fixture
def case(tmp_path, monkeypatch):
    frozen, results, home = tmp_path / "frozen", tmp_path / "results", tmp_path / "home"
    frozen.mkdir(); results.mkdir(); (home / "sessions").mkdir(parents=True)
    sample = results / m.SLOT
    (sample / "responses").mkdir(parents=True)
    monkeypatch.setattr(m, "HOME", home)
    schema = (HERE / "arms/compact.schema.json").read_bytes()
    source, prompt = b"Synthetic passage.", b"Judge this synthetic passage."
    artifacts = {"context.txt": b"Synthetic context.", "source.txt": source, "prompt.txt": prompt, "schema.json": schema}
    for name, raw in artifacts.items(): (frozen / name).write_bytes(raw)
    ids = json.loads(schema)["properties"]["result"]["properties"]["dimensions"]["items"]["properties"]["dimension_id"]["enum"]
    response = {"status": "SCORED", "abstention_reason": None, "result": {"method": "compact_analytic_ttcw_v1",
        "dimensions": [{"dimension_id": key, "score": 3, "rationale": "Synthetic observation.",
                        "evidence": [{"quote": "Synthetic passage.", "explanation": "Synthetic evidence."}]} for key in ids],
        "overall_score": 3, "overall_rationale": "Synthetic assessment."}}
    sid = "570aad3892cf" + "a" * 52
    row = {"endpoint": "sol", "endpoint_ordinal": 391, "logical_sample_id": sid, "arm": "compact",
           "sources": [{"id": "story", "input_path": "source.txt", "sha256": m.digest(source)}],
           "prompt_path": "prompt.txt", "prompt_sha256": m.digest(prompt), "prompt_bytes": len(prompt),
           "schema_path": "schema.json", "schema_sha256": m.digest(schema), "schema_bytes": len(schema)}
    row["request_sha256"] = m.digest(m.canonical(row))
    manifest = {"requests": [row], "artifacts": {name: {"sha256": m.digest(raw), "bytes": len(raw)} for name, raw in artifacts.items()},
                "implementation": {"semantic_validator_sha256": m.VALIDATOR_SHA,
                    "schema_subset_sha256": m.digest((m.TOOLS / "model_work_queue/adapters/json_schema_subset.py").read_bytes())}}
    manifest_raw = m.canonical(manifest)
    (frozen / "manifest.json").write_bytes(manifest_raw)
    job = {"manifest_sha256": m.digest(manifest_raw), "endpoint": "sol", "model": "gpt-6.1-sol", "reasoning": "high",
           "automatic_retries": 0, "zero_charge_only": True, "receipt_reader_sha256": m.READER_SHA,
           "validator_sha256": m.VALIDATOR_SHA,
           "account_identity_sha256": "4392760f900d3f082618c27721f07cbc9ffca06b91bb9ac8fa5f20695625d2de",
           "helper_sha256": "c0a3563dab36105830c9e63be7fdeb551ef7a9805a5b5b44450c9e6501be3b01"}
    (results / "job.json").write_bytes(m.canonical(job))
    rollout, events, final = f.native_fixture(sample, prompt.decode(), m.canonical(response).decode())
    rollout[0]["timestamp"] = "2026-10-05T01:01:39Z"
    rollout[-1]["timestamp"] = "2026-10-05T01:04:39Z"
    transport = m.load("sol391_synthetic_transport", REPO / "evaluation-results/hbq-native-transport-recovery-v1/reconcile.py")
    events.insert(3, {"type": "error", "message": "Reconnecting... 2/5 (" + transport.SOL_WS + ")"})
    events_raw = f.raw(events)
    stem = sample / "responses/batch-0001.attempt-0001"
    Path(str(stem) + ".events.jsonl").write_bytes(events_raw)
    Path(str(stem) + ".message.json").write_bytes(final)
    own = home / "sessions/own-rollout.jsonl"
    own.write_bytes(f.raw(rollout))
    terminal = {"state": "unadmitted_no_resend", "accepted": False, "no_resend": True,
                "error_class": "_ProviderAttemptFailure", "error": "timeout after -3128.9529999999795 seconds",
                "provider_record": {"provider_artifacts": {"codex_events": {"path": "responses/batch-0001.attempt-0001.events.jsonl",
                    "sha256": m.digest(events_raw), "bytes": len(events_raw)}}}}
    files = {"condition": (sample / "condition.json", m.canonical(row)),
        "started": (sample / "attempt-started.json", m.canonical({"time": "2026-10-05T01:01:38Z", "session_id": None,
                                                        "state": "before_contact", "no_resend": True})),
        "identity": (sample / "native-identity.json", m.canonical({"logical_sample_id": sid, "session_id": None})),
        "terminal": (sample / "terminal.json", m.canonical(terminal)), "manifest": (frozen / "manifest.json", manifest_raw),
        "job": (results / "job.json", m.canonical(job)), "events": (Path(str(stem) + ".events.jsonl"), events_raw),
        "final": (Path(str(stem) + ".message.json"), final), "rollout": (own, f.raw(rollout))}
    for path, raw in files.values(): path.write_bytes(raw)
    (sample / "schema.json").write_bytes(schema)
    monkeypatch.setattr(m, "PINNED", {name: (m.digest(raw), len(raw)) for name, (_, raw) in files.items()})
    monkeypatch.setattr(m, "PROJECTION_SHA", m.digest(transport.sol_projection(events_raw)[0]))
    return {"frozen": frozen, "results": results, "home": home, "sample": sample, "rollout": own,
            "files": files, "row": row, "artifacts": artifacts, "transport": transport, "events": events}


def reconcile(case, **kwargs):
    return m.reconcile(case["frozen"] / "manifest.json", case["results"], m.SLOT, case["home"], case["rollout"], **kwargs)


def snapshot(case, output):
    receipt, response, acceptance, reads = reconcile(case)
    output.mkdir()
    for name, raw in reads.raws.items():
        path = output / receipt["source_commitments"][name]["snapshot"]
        path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(raw)
    (output / "reconciliation.json").write_bytes(m.canonical(receipt))
    (output / "response.json").write_bytes(response)
    (output / "acceptance.json").write_bytes(m.canonical(acceptance))
    (output / "terminal.json").write_bytes(m.canonical({"state": receipt["state"], "no_resend": True,
        "reconciliation_sha256": m.digest(m.canonical(receipt))}))
    return receipt


def test_native_descendant_replays_snapshots_without_original_files_and_retains_failure(case, tmp_path):
    out = tmp_path / "descendant"
    receipt = snapshot(case, out)
    assert receipt["accepted"] and not receipt["abstention"]
    assert receipt["provider_calls_made"] == receipt["new_logical_votes"] == 0
    assert not receipt["native"]["original_receipt_policy_satisfied"]
    original_terminal = case["files"]["terminal"][1]
    for path, _ in case["files"].values(): path.unlink()
    actual, _, _, reads = reconcile(case, snapshot=out, commitments=receipt["source_commitments"])
    assert actual == receipt and reads.raws["terminal"] == original_terminal


@pytest.mark.parametrize("damage", ["source", "condition", "missing_snapshot_pin", "projection"])
def test_changed_source_or_snapshot_fails_without_fallback(case, tmp_path, damage):
    out = tmp_path / "descendant"
    receipt = snapshot(case, out)
    if damage == "source":
        (case["frozen"] / "source.txt").write_bytes(b"Changed passage.")
        with pytest.raises(ValueError, match="Frozen artifact"): reconcile(case)
    elif damage == "condition":
        case["files"]["condition"][0].write_bytes(b"{}")
        with pytest.raises(ValueError, match="Pinned source"): reconcile(case)
    else:
        pins = deepcopy(receipt["source_commitments"])
        if damage == "missing_snapshot_pin": pins.pop("condition")
        else: (out / pins["events_projection"]["snapshot"]).write_bytes(b"Changed projection\n")
        with pytest.raises(ValueError, match="Snapshot|snapshot"):
            reconcile(case, snapshot=out, commitments=pins)


def test_same_bytes_cannot_alias_another_cwd_or_account(case, tmp_path):
    with pytest.raises(ValueError, match="account/session"):
        m.reconcile(case["frozen"] / "manifest.json", case["results"], m.SLOT, tmp_path / "other-account", case["rollout"])
    import shutil
    alias = tmp_path / "alias"
    shutil.copytree(case["results"], alias)
    with pytest.raises(ValueError):
        m.reconcile(case["frozen"] / "manifest.json", alias, m.SLOT, case["home"], case["rollout"])


def test_completed_routing_errors_do_not_extend_391_policy_or_resend_392(case):
    events = deepcopy(case["events"])
    events[3]["message"] = "Reconnecting... 2/5 (workspace routing discovery failed)"
    assert events[-1]["type"] == "turn.completed"
    with pytest.raises(ValueError, match="Unknown native transport error"):
        case["transport"].sol_projection(f.raw(events))
    with pytest.raises(ValueError, match="no resend"):
        m.reconcile(case["frozen"] / "manifest.json", case["results"], "0392-be39ffd1004a", case["home"], case["rollout"])


def test_completed_own_final_with_invalid_quote_is_rejected(case, monkeypatch):
    path, _ = case["files"]["final"]
    response = json.loads(path.read_bytes())
    response["result"]["dimensions"][0]["evidence"][0]["quote"] = "Absent quotation."
    final = m.canonical(response)
    events = deepcopy(case["events"]); events[-2]["item"]["text"] = final.decode()
    rollout = [json.loads(line) for line in case["rollout"].read_bytes().splitlines()]
    rollout[8]["payload"]["content"][0]["text"] = final.decode()
    rollout[-1]["payload"]["last_agent_message"] = final.decode()
    path.write_bytes(final); case["rollout"].write_bytes(f.raw(rollout))
    event_path = case["files"]["events"][0]; event_path.write_bytes(f.raw(events))
    terminal_path = case["files"]["terminal"][0]
    terminal = json.loads(terminal_path.read_bytes())
    terminal["provider_record"]["provider_artifacts"]["codex_events"].update(sha256=m.digest(f.raw(events)), bytes=len(f.raw(events)))
    terminal_path.write_bytes(m.canonical(terminal))
    for name in ("final", "rollout", "events", "terminal"):
        raw = case["files"][name][0].read_bytes(); m.PINNED[name] = (m.digest(raw), len(raw))
    monkeypatch.setattr(m, "PROJECTION_SHA", m.digest(case["transport"].sol_projection(f.raw(events))[0]))
    receipt, _, acceptance, _ = reconcile(case)
    assert not acceptance["accepted"] and "substring" in acceptance["errors"][0]
    assert receipt["state"] == "completed_semantically_rejected" and receipt["no_resend"]


def test_analysis_join_replaces_one_failure_retains_denominator_and_labels_closed(case, tmp_path):
    out = tmp_path / "descendant"
    receipt = snapshot(case, out)
    loaded = a.modules(); loaded["reconcile_sol_transport"] = m
    row = case["row"]; identity = ("sol", row["logical_sample_id"])
    record = {"request": row, "state": "unadmitted_no_resend", "accepted": None,
              "terminal_sha256": m.PINNED["terminal"][0], "source_index": 0}
    joined = {identity: record, ("grok", "untouched"): {"state": "not_collected"}}
    source = {"endpoint": "sol", "manifest_path": str(case["frozen"] / "manifest.json"),
              "manifest_sha256": m.PINNED["manifest"][0], "job_sha256": m.PINNED["job"][0], "results_root": str(case["results"])}
    spec = {"path": str(out / "reconciliation.json"), "sha256": m.digest(m.canonical(receipt))}
    wrong = dict(source, job_sha256="wrong-chain")
    with pytest.raises(ValueError, match="source lineage"):
        a.apply_reconciliation(spec, joined, [wrong], case["artifacts"], loaded, None)
    a.apply_reconciliation(spec, joined, [source], case["artifacts"], loaded, None)
    assert len(joined) == 2 and record["original_state"] == "unadmitted_no_resend" and record["state"] == "accepted"
    assert record["accepted"]["request"] == row
    with pytest.raises(ValueError, match="one original failed slot"):
        a.apply_reconciliation(spec, joined, [source], case["artifacts"], loaded, None)
    with pytest.raises(ValueError, match="every original planned"):
        a.label_release_gate(joined, expected=2)


def test_private_output_rejects_existing_or_input_alias(tmp_path):
    source = tmp_path / "source"; source.mkdir()
    with pytest.raises(ValueError): m.fresh_output(source, [source])
    with pytest.raises(ValueError): m.fresh_output(source / "new", [source])
    assert m.fresh_output(tmp_path / "new", [source]) == tmp_path / "new"
