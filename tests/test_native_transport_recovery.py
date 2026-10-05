"""Synthetic saved-native recovery witnesses; no provider or account proof."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

REPO = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("bounded_transport_recovery", REPO / "evaluation-results/hbq-native-transport-recovery-v1/reconcile.py")
r = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = r
spec.loader.exec_module(r)
spec = importlib.util.spec_from_file_location("transport_native_fixture", REPO / "tests/test_codex_receipts.py")
f = importlib.util.module_from_spec(spec)
spec.loader.exec_module(f)


def mfa_lifecycle_fixture(name):
    previous = sys.modules.get("prepare")
    paths = list(sys.path)
    try:
        sys.modules["prepare"] = r.load(name + "_prepare", REPO / "evaluation-results/hbq-matched-mfa-v1/prepare.py")
        return r.load(name, REPO / "tests/test_matched_mfa_collection.py")
    finally:
        sys.path[:] = paths
        if previous is None:
            sys.modules.pop("prepare", None)
        else:
            sys.modules["prepare"] = previous


def sol_files(tmp_path):
    sample = tmp_path / "sample"
    (sample / "responses").mkdir(parents=True)
    prompt = "Judge this synthetic passage."
    rollout, events, final = f.native_fixture(sample, prompt)
    rollout[0]["timestamp"] = "2026-10-05T01:01:39Z"
    rollout[-1]["timestamp"] = "2026-10-05T01:04:39Z"
    events.insert(3, {"type": "error", "message": "Reconnecting... 2/5 (" + r.SOL_WS + ")"})
    events.insert(4, {"type": "item.completed", "item": {"id": "retry", "type": "error", "message": r.SOL_FALLBACK}})
    stem = sample / "responses/batch-0001.attempt-0001"
    Path(str(stem) + ".events.jsonl").write_bytes(f.raw(events))
    Path(str(stem) + ".message.json").write_bytes(final)
    own = tmp_path / "rollout.jsonl"
    own.write_bytes(f.raw(rollout))
    return sample, own, prompt, events, rollout, final


def test_sol_projection_preserves_raw_and_replays_without_home_logs(tmp_path):
    sample, own, prompt, events, rollout, final = sol_files(tmp_path)
    original = Path(str(sample / "responses/batch-0001.attempt-0001") + ".events.jsonl").read_bytes()
    reads = r.ReadSet()
    answer, proof = r.recover_sol(reads, sample, prompt, tmp_path / "no-home", {"time": "2026-10-05T01:01:38Z"}, own)
    assert answer == {"verdicts": []}
    assert proof["raw_events_sha256"] != proof["filtered_events_sha256"]
    assert not proof["original_receipt_policy_satisfied"]
    assert len(proof["diagnostics"]) == 2
    assert Path(str(sample / "responses/batch-0001.attempt-0001") + ".events.jsonl").read_bytes() == original
    commitments = reads.commitments()
    snapshot = tmp_path / "snapshot"
    for name, raw in reads.raws.items():
        p = snapshot / commitments[name]["snapshot"]
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(raw)
    own.unlink()
    replay, _ = r.recover_sol(r.ReadSet(snapshot, commitments), sample, prompt, tmp_path / "no-home", {"time": "2026-10-05T01:01:38Z"})
    assert replay == answer


@pytest.mark.parametrize("damage", ["unknown_error", "foreign_thread", "tool", "second_turn", "missing_final", "prompt", "model", "effort", "start_time"])
def test_sol_recovery_rejects_unbound_or_unknown_native_evidence(tmp_path, damage):
    sample, own, prompt, events, rollout, final = sol_files(tmp_path)
    started = {"time": "2026-10-05T01:01:38Z"}
    if damage == "unknown_error": events[3]["message"] = "Authentication failed"
    elif damage == "foreign_thread": events[3]["thread_id"] = f.FOREIGN
    elif damage == "tool": events.insert(-1, {"type": "item.completed", "item": {"type": "command_execution"}})
    elif damage == "second_turn": events.insert(-1, {"type": "turn.started"})
    elif damage == "missing_final": events.pop()
    elif damage == "prompt": prompt += " altered"
    elif damage == "model": rollout[5]["payload"]["model"] = "another-model"
    elif damage == "effort": rollout[5]["payload"]["effort"] = "low"
    elif damage == "start_time": started["time"] = "2026-10-06T00:00:00Z"
    Path(str(sample / "responses/batch-0001.attempt-0001") + ".events.jsonl").write_bytes(f.raw(events))
    own.write_bytes(f.raw(rollout))
    with pytest.raises(ValueError):
        r.recover_sol(r.ReadSet(), sample, prompt, tmp_path / "home", started, own)


def grok_updates():
    ids = iter(range(1, 10))
    def row(kind, content=None):
        update = {"sessionUpdate": kind}
        meta = {"eventId": "event-" + str(next(ids)), "agentTimestampMs": 1}
        if content is not None:
            update["content"] = {"type": "text", "text": content}
            if kind != "user_message_chunk":
                meta.update(promptId="own-request", totalTokens=1, streamStartMs=1, turnStartMs=1, chunkId=1,
                            updateType="AgentThoughtChunk" if kind == "agent_thought_chunk" else "AgentMessageChunk")
            else: update["_meta"] = {"modelId": "grok-4.7", "promptIndex": 0}
        if kind == "turn_completed": update.update(elapsed_ms=100, prompt_id="own-request", stop_reason="end_turn", usage={})
        return {"timestamp": "2026-10-05T01:01:40Z", "method": "_x.ai/session/update" if kind in {"retry_state", "turn_completed"} else "session/update",
                "params": {"sessionId": "own-session", "_meta": meta, "update": update}}
    retries = []
    for index, reason in enumerate([r.GROK_DECODE, r.GROK_DNS], 1):
        v = row("retry_state")
        v["params"]["update"].update(type="retrying", attempt=index, max_retries=15, reason=reason, error_type="http")
        retries.append(v)
    return [row("user_message_chunk", "Exact prompt"), *retries, row("agent_thought_chunk", "Synthetic thought"),
            row("agent_message_chunk", '{"verdicts":[]}'), row("turn_completed")]


def test_grok_retry_projection_is_separate_and_preserves_own_update_order():
    rows = grok_updates()
    before = deepcopy(rows)
    filtered, diagnostics = r.grok_projection(rows, {"created_at": "2026-10-05T01:01:39Z", "updated_at": "2026-10-05T01:04:00Z", "request_id": "own-request", "reasoning_effort": "high"}, "own-session", "Exact prompt")
    assert rows == before
    assert filtered == [rows[i] for i in [0, 3, 4, 5]]
    assert len(diagnostics) == 2


@pytest.mark.parametrize("damage", ["unknown_retry", "foreign_session", "late_retry", "tool", "duplicate_terminal", "wrong_prompt", "wrong_time", "wrong_effort"])
def test_grok_projection_rejects_other_native_states(damage):
    rows = grok_updates()
    summary = {"created_at": "2026-10-05T01:01:39Z", "updated_at": "2026-10-05T01:04:00Z", "request_id": "own-request", "reasoning_effort": "high"}
    if damage == "unknown_retry": rows[1]["params"]["update"]["reason"] = "Allowance exhausted"
    elif damage == "foreign_session": rows[1]["params"]["sessionId"] = "foreign"
    elif damage == "late_retry": rows[1], rows[4] = rows[4], rows[1]
    elif damage == "tool": rows[3]["params"]["update"]["sessionUpdate"] = "tool_call"
    elif damage == "duplicate_terminal": rows.append(deepcopy(rows[-1]))
    elif damage == "wrong_prompt": rows[0]["params"]["update"]["content"]["text"] = "Different prompt"
    elif damage == "wrong_time": rows[1]["timestamp"] = "2026-10-06T01:01:40Z"
    elif damage == "wrong_effort": summary["reasoning_effort"] = "low"
    with pytest.raises(ValueError):
        r.grok_projection(rows, summary, "own-session", "Exact prompt")


@pytest.fixture
def failed_slot(monkeypatch):
    """Mock call-path fixture; native transport correctness is tested above."""
    fixture = mfa_lifecycle_fixture("transport_lifecycle_fixture")
    case = fixture.MatchedMFACollectionTests()
    case.setUp()
    module = fixture.c
    home = Path(case.temp.name) / "collection-accounts/cwr-sol-secondary"
    case.binding["runtime"]["secondary_home_sha256"] = r.digest(str(home.resolve()).encode())
    (case.output / "job.json").write_bytes(module.prepare.canonical(case.binding))
    (case.output / "account-binding.json").write_bytes(module.prepare.canonical(module.account_receipt(case.binding)))
    case.row["request_sha256"] = "f" * 64
    context = {"module": module, "manifest": case.manifest, "root": case.root,
               "subset": case.subset, "validator": case.validator}
    receipt = {"config": {"manifest_sha256": case.binding["manifest_sha256"], "secondary_home_local_only": str(home)}}
    wrapper = r.load("transport_mock_continuation", REPO / "evaluation-results/hbq-native-transport-recovery-v1/collector.py")
    monkeypatch.setattr(wrapper, "recon", r)
    def failure(**kwargs):
        kwargs["before_provider_attempt"]()
        raise TimeoutError("Mock failure before native receipt admission")
    assert case.collect(failure) == "unadmitted_no_resend"
    try:
        yield case, context, receipt, wrapper
    finally:
        case.doCleanups()


@pytest.mark.parametrize("damage", [None, "schema", "grounding"])
def test_completed_saved_response_is_one_descendant_or_settled_missingness(failed_slot, monkeypatch, damage):
    case, context, receipt, wrapper = failed_slot
    answer = deepcopy(case.answer)
    if damage == "schema": answer["result"]["score"] = 8
    if damage == "grounding": answer["result"]["evidence"][0]["quote"] = "Invented quote"
    monkeypatch.setattr(r, "recover_sol", lambda *a, **kw: (answer, {"mock_only": True}))
    sample = context["module"].sample_path(case.output, case.row)
    original = (sample / "terminal.json").read_bytes()
    expected = "accepted" if damage is None else "semantic_rejected"
    assert wrapper.recover_current(sample, case.row, receipt, context, case.binding) == (expected, True)
    assert (sample / "terminal.json").read_bytes() == original
    state, replayed, recovered = wrapper.replay_sample(sample, case.row, receipt, context, case.binding)
    assert (state, recovered) == (expected, True)
    assert replayed == (answer if damage is None else None)
    with pytest.raises(FileExistsError): case.collect()
    effective = json.loads((sample / "effective-terminal.json").read_bytes())
    assert effective["new_votes"] == 0 and effective["no_resend"]
    effective["reconciliation_sha256"] = "0" * 64
    (sample / "effective-terminal.json").write_bytes(r.canonical(effective))
    with pytest.raises(ValueError):
        wrapper.replay_sample(sample, case.row, receipt, context, case.binding)


def test_unknown_native_failure_remains_reserved_without_effective_promotion(failed_slot, monkeypatch):
    case, context, receipt, wrapper = failed_slot
    def unknown(*args, **kwargs): raise ValueError("Unknown native transport error")
    monkeypatch.setattr(r, "recover_sol", unknown)
    sample = context["module"].sample_path(case.output, case.row)
    assert wrapper.recover_current(sample, case.row, receipt, context, case.binding) == ("unadmitted_no_resend", False)
    assert not (sample / "effective-terminal.json").exists()
    assert not (sample / "transport-reconciliation.json").exists()


def test_suffix_selection_preserves_original_order_and_reserves_every_contacted_identity():
    wrapper = r.load("transport_suffix_test", REPO / "evaluation-results/hbq-native-transport-recovery-v1/collector.py")
    manifest = {"requests": [{"endpoint": "sol", "endpoint_ordinal": n, "request_sha256": str(n),
        "logical_sample_id": str(n)} for n in range(1, 5)]}
    receipt = {"reserved_through": {"sol": 2}, "untouched_request_sha256s": {"sol": ["3", "4"]}}
    assert [row["endpoint_ordinal"] for row in wrapper.suffix_rows(manifest, receipt, "sol")] == [3, 4]
    receipt["untouched_request_sha256s"]["sol"] = ["2", "3", "4"]
    with pytest.raises(ValueError): wrapper.suffix_rows(manifest, receipt, "sol")


def test_join_rejects_duplicate_reserved_votes_and_keeps_full_missing_denominator(tmp_path):
    analysis = r.load("transport_join_test", REPO / "evaluation-results/hbq-native-transport-recovery-v1/analysis.py")
    rows = [{"endpoint": endpoint, "endpoint_ordinal": n, "logical_sample_id": endpoint + str(n),
             "request_sha256": endpoint + str(n)} for endpoint in ("sol", "grok") for n in (1, 2)]
    prefix = {**rows[0], "state": "semantic_rejected", "response": None, "transport_recovered": True}
    receipt = {"prefix": [prefix], "planned_denominator": 4, "reserved_through": {"sol": 1, "grok": 0},
               "untouched_request_sha256s": {"sol": ["sol2"], "grok": ["grok1", "grok2"]}}
    context = {"manifest": {"requests": rows}, "module": SimpleNamespace(sample_path=lambda output, row: output / row["logical_sample_id"])}
    outputs = {endpoint: tmp_path / endpoint for endpoint in ("sol", "grok")}
    records, inventory = analysis.joined_evidence(receipt, "mock", context, outputs)
    assert records == [] and len(inventory) == 4
    assert [i["state"] for i in inventory] == ["semantic_rejected", "untouched", "untouched", "untouched"]
    receipt["prefix"].append(deepcopy(prefix))
    with pytest.raises(ValueError): analysis.joined_evidence(receipt, "mock", context, outputs)


@pytest.mark.parametrize("stopped", [False, True])
def test_validate_only_and_stop_boundary_do_not_load_account_or_provider(tmp_path, monkeypatch, stopped):
    fixture = mfa_lifecycle_fixture("transport_boundary_fixture")
    wrapper = r.load("transport_boundary_collector", REPO / "evaluation-results/hbq-native-transport-recovery-v1/collector.py")
    row = {"endpoint": "sol", "endpoint_ordinal": 1, "logical_sample_id": "synthetic", "request_sha256": "committed"}
    root, receipt_root = tmp_path / "frozen", tmp_path / "receipt"
    output = tmp_path / "continuation"
    receipt = {"config": {"sources": [{"root_local_only": str(tmp_path / "source")}],
                          "secondary_home_local_only": str(tmp_path / "account"), "grok_sessions_root_local_only": str(tmp_path / "history")},
               "reserved_through": {"sol": 0}, "untouched_request_sha256s": {"sol": ["committed"]}, "planned_denominator": 1}
    context = {"module": fixture.c, "manifest": {"requests": [row]}, "root": root}
    binding = {"reserved_prefix": 0}
    monkeypatch.setattr(wrapper.recon, "verify", lambda *args: (receipt, context))
    monkeypatch.setattr(wrapper, "job_binding", lambda *args: binding)
    def forbidden(*args, **kwargs): raise AssertionError("Account/provider import crossed boundary")
    monkeypatch.setattr(wrapper.recon, "load", forbidden)
    args = ["collector.py", "--reconciliation", str(receipt_root / "reconciliation.json"),
            "--reconciliation-sha256", "mock", "--endpoint", "sol", "--results-dir", str(output)]
    if stopped:
        output.mkdir()
        (output / "job.json").write_bytes(r.canonical(binding))
        (output / "STOP").touch()
    else:
        args.append("--validate-only")
    monkeypatch.setattr(sys, "argv", args)
    assert wrapper.main() == (3 if stopped else 0)
    if stopped:
        note = json.loads((output / "stop-observed.json").read_bytes())
        assert note["cooperative_cancellation_claimed"] is False
    else:
        assert not output.exists()
