"""Synthetic persistence boundaries; these do not attest native execution."""
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

REPO = Path(__file__).resolve().parents[1]
PATH = REPO / "evaluation-results/hbq-mfa-conditional-benchmark-v1/analysis_chain_v2.py"


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes((json.dumps(value, sort_keys=True) + "\n").encode())


def test_named_suffix_owning_return_and_full_gate(tmp_path, monkeypatch):
    a = load("conditional_v2_lifecycle_test", PATH)
    launcher = tmp_path / "launcher.py"
    launcher.write_bytes(b"# synthetic owned-launcher contract\n")
    launchsha = a.sha(launcher.read_bytes())
    monkeypatch.setattr(a, "LAUNCHERS", {(a.SUFFIX_POLICY, "grok"): (launcher, launchsha)})
    life, output = tmp_path / "life", tmp_path / "output"
    manifest = tmp_path / "manifest.json"
    route = Path.home() / ".codex/state/model-work-queue-cwr-placeholder-r31"
    argv = [str(a.REPO / ".venv/Scripts/python.exe"), "-B", str(a.SUFFIX_PATH), "--manifest", str(manifest),
        "--manifest-sha256", a.SUFFIX_MANIFEST_SHA, "--results-dir", str(output), "--route-root", str(route),
        "--route-sha256", "r", "--workers", "2", "--endpoint-headroom", "2", "--stop-path", str(life / "STOP"),
        "--owner-lifecycle-root", str(life), "--execute-native", "--owner-global-headroom-verified", "--owner-current-route-verified"]
    inv = {"argv": argv, "owner": a.OWNER, "launcher_sha256": launchsha, "collector_sha256": a.SUFFIX_SHA,
        "manifest_sha256": a.SUFFIX_MANIFEST_SHA, "route_sha256": "r", "workers": 2, "time": "2026-10-06T01:00:00Z",
        "minimum_launch_free_disk_bytes": 1073741824,
        "no_resend": True, "owner_attestations": dict.fromkeys(("global_headroom_verified", "current_route_verified",
            "mfa85_grok2_released", "outbound_disclosure_acknowledged"), True)}
    write(life / "invocation.json", inv)
    invsha = a.sha((life / "invocation.json").read_bytes())
    write(life / "run-started.json", {"argv": argv, "invocation_sha256": invsha, "launcher_sha256": launchsha,
        "time": "2026-10-06T01:00:02Z", "no_resend": True})
    native = {"argv": argv, "cwd": str(a.REPO), "pid": 2, "no_resend": True,
        "process_creation_utc": "2026-10-06T01:00:03Z", "creation_time_basis": "Windows GetProcessTimes on owned Popen handle"}
    write(life / "native-handle.json", native)
    handle = dict(native, pid=1, process_creation_utc="2026-10-06T01:00:01Z", workers=2,
        argv=[str(a.REPO / ".venv/Scripts/python.exe"), "-B", str(launcher), "--run"],
        lifecycle=str(life), native_job=str(output / "job.json"))
    write(life / "handle.json", handle)
    outer = {"exit_code": 3, "no_resend": True, "invocation_sha256": invsha, "native_exit_confirmed": True,
        "time": "2026-10-06T01:00:04Z"}
    write(life / "terminal.json", outer)
    source = {"collector_policy": a.SUFFIX_POLICY, "endpoint": "grok", "manifest_path": str(manifest),
        "manifest_sha256": a.SUFFIX_MANIFEST_SHA, "results_root": str(output), "job_sha256": "j",
        "lifecycle": {name: {"path": str(launcher if name == "launcher" else life / {
            "outer_terminal": "terminal.json", "invocation": "invocation.json", "run_started": "run-started.json",
            "native_handle": "native-handle.json", "handle": "handle.json"}[name]), "sha256": a.sha((launcher if name == "launcher" else life / {
            "outer_terminal": "terminal.json", "invocation": "invocation.json", "run_started": "run-started.json",
            "native_handle": "native-handle.json", "handle": "handle.json"}[name]).read_bytes())} for name in a.LIFECYCLE_NAMES}}
    job = {"collector_sha256": a.SUFFIX_SHA, "manifest_sha256": a.SUFFIX_MANIFEST_SHA, "workers": 2,
        "owner_declared_endpoint_headroom": 2, "owner_lifecycle_invocation_sha256": invsha,
        "owner_lifecycle_root": str(life), "external_stop_path": str(life / "STOP"), "endpoint": "grok", "route_sha256": "r"}
    job.update(persistence_guard_policy="conditional_contact_time_minimum_free_disk_v1", minimum_free_disk_bytes=268435456)
    proof, _, _ = a.verify_lifecycle(source, job)
    assert proof["verified"] and proof["owning_wrapper_raw_invocation_argument"] is False
    inv["owner_attestations"]["current_route_verified"] = False
    write(life / "invocation.json", inv)
    invsha2 = a.sha((life / "invocation.json").read_bytes())
    source["lifecycle"]["invocation"]["sha256"] = invsha2
    outer["invocation_sha256"] = invsha2
    write(life / "terminal.json", outer)
    source["lifecycle"]["outer_terminal"]["sha256"] = a.sha((life / "terminal.json").read_bytes())
    start = json.loads((life / "run-started.json").read_bytes())
    start["invocation_sha256"] = invsha2
    write(life / "run-started.json", start)
    source["lifecycle"]["run_started"]["sha256"] = a.sha((life / "run-started.json").read_bytes())
    job["owner_lifecycle_invocation_sha256"] = invsha2
    with pytest.raises(ValueError, match="actual execution and all owning attestations"):
        a.verify_lifecycle(source, job)
    source["collector_policy"] = "invented_alias"
    with pytest.raises(ValueError, match="Unpinned"):
        a.verify_lifecycle(source, job)
    # The Sol native child runs the unchanged scientific argv through a pinned
    # augmentation, with its own additional collector-start receipt.
    monkeypatch.setattr(a, "LAUNCHERS", {(a.ORIGINAL_POLICY, "sol"): (launcher, launchsha)})
    sol_argv = [str(a.HERE / "collector.py"), "--manifest", str(manifest), "--manifest-sha256", a.MANIFEST_SHA,
        "--results-dir", str(output), "--endpoint", "sol", "--workers", "2", "--endpoint-headroom", "2", "--payload-classification", "public_repo"]
    child_argv = [str(a.REPO / ".venv/Scripts/python.exe"), "-B", str(launcher), "--native-run"]
    augmentation = {"policy": "conditional_sol_disk_stop_before_contact_v1", "guard_source_sha256": launchsha,
        "min_launch_free_bytes": 1073741824, "min_contact_free_bytes": 268435456,
        "original_callback_preserved": True, "original_collector_job_and_admission_unchanged": True}
    inv.update(policy="conditional_sol2_after_exact_lamp_disk_gap_terminal_join_v1", argv=sol_argv, native_argv=child_argv,
        collector_sha256=a.ORIGINAL_SHA, manifest_sha256=a.MANIFEST_SHA, extraction_sha256="e", source_release={},
        runtime_augmentation=augmentation, owner_attestations=dict.fromkeys(("global_headroom_verified", "lamp_sol2_released", "outbound_disclosure_acknowledged"), True))
    write(life / "invocation.json", inv)
    solsha = a.sha((life / "invocation.json").read_bytes())
    start.update(argv=child_argv, invocation_sha256=solsha, source_release_sha256=a.sha(b"{}\n"))
    write(life / "run-started.json", start)
    native["argv"] = child_argv
    write(life / "native-handle.json", native)
    collector_start = {"argv": sol_argv, "invocation_sha256": solsha, "runtime_augmentation": augmentation["policy"],
        "no_resend": True, "time": "2026-10-06T01:00:03Z"}
    write(life / "collector-run-started.json", collector_start)
    outer["invocation_sha256"] = solsha
    write(life / "terminal.json", outer)
    source.update(collector_policy=a.ORIGINAL_POLICY, endpoint="sol", manifest_sha256=a.MANIFEST_SHA)
    source["lifecycle"]["collector_run_started"] = {"path": str(life / "collector-run-started.json"), "sha256": "pending"}
    for name, pin in source["lifecycle"].items():
        pin["sha256"] = a.sha(Path(pin["path"]).read_bytes())
    job.update(collector_sha256=a.ORIGINAL_SHA, manifest_sha256=a.MANIFEST_SHA, endpoint="sol", payload_classification="public_repo", extraction_sha256="e")
    sol_proof, _, _ = a.verify_lifecycle(source, job)
    assert sol_proof["verified"] and sol_proof["runtime_augmentation"] == augmentation
    collector_start["runtime_augmentation"] = "unreviewed_alias"
    write(life / "collector-run-started.json", collector_start)
    source["lifecycle"]["collector_run_started"]["sha256"] = a.sha((life / "collector-run-started.json").read_bytes())
    with pytest.raises(ValueError, match="collector start differs"):
        a.verify_lifecycle(source, job)
    ledger = [{"endpoint": endpoint, "logical_sample_id": str(n), "state": "unadmitted_no_resend",
        "terminal_verified": True, "original_strict_native_verified": False} for endpoint in ("sol", "grok") for n in range(5170)]
    proofs = [dict(proof, endpoint=e) for e in ("sol", "grok")]
    a.label_gate(ledger, proofs, True)
    with pytest.raises(ValueError):
        a.label_gate(ledger, proofs, False)
    with pytest.raises(ValueError):
        a.label_gate(ledger, proofs + [dict(proof, verified=False)], True)
    ledger[-1]["state"] = "started_unresolved"
    with pytest.raises(ValueError):
        a.label_gate(ledger, proofs, True)


def test_failed_native_missing_vote_identity_and_closed_metadata(tmp_path, monkeypatch, capsys):
    a = load("conditional_v2_failed_test", PATH)
    # Extract the actual pinned suffix replay body without importing its runtime.
    import ast
    tree = ast.parse(a.checked(a.SUFFIX_PATH, a.SUFFIX_SHA))
    replay = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "replay")
    denied = Mock(side_effect=AssertionError("Failed disposition must not read an answer"))
    c = SimpleNamespace(SETTLED={"accepted", "semantic_rejected"}, pinned=lambda root, name, pin: a.checked(root / name, pin["sha256"]))
    scope = {"json": json, "require": a.require, "sha": a.sha, "MANIFEST_SHA": a.SUFFIX_MANIFEST_SHA,
        "conditional": c, "v3": SimpleNamespace(SETTLED=c.SETTLED, FAILED={"unadmitted_no_resend"}, validate_native=denied), "inputs": denied}
    exec(compile(ast.Module(body=[replay], type_ignores=[]), "actual_failed_suffix_replay", "exec"), scope)
    sample = tmp_path / "output/0069-synthetic"
    session = "fce76243-a938-4c0b-9d97-5061ecfba174"
    row = {"endpoint": "grok", "logical_sample_id": "logical", "request_sha256": "request"}
    job = {"policy": a.SUFFIX_POLICY}
    write(sample.parent / "job.json", job)
    write(sample / "condition.json", row)
    write(sample / "native-identity.json", {"logical_sample_id": "logical", "session_id": session})
    # A late completed envelope can carry an excluded malformed JSON string.
    # Field projection must retain its request ID without decoding output.
    (sample / "native-result.json").write_bytes(b'{"state":"completed","result":{"runtime":{"request_id_hash":"' + b"a" * 64 + b'"},"output":{"prose":"\\q"}}}')
    retained = {name: {"sha256": a.sha((sample / name).read_bytes())} for name in ("condition.json", "native-identity.json", "native-result.json")}
    terminal = {"state": "unadmitted_no_resend", "accepted": False, "logical_sample_id": "logical", "no_resend": True,
        "manifest_sha256": a.SUFFIX_MANIFEST_SHA, "job_sha256": a.sha((sample.parent / "job.json").read_bytes()),
        "retained_artifacts": retained, "retention_errors": []}
    write(sample / "terminal.json", terminal)
    got, answer = scope["replay"](sample, row, {}, job, tmp_path, None, None)
    assert got["state"] == "unadmitted_no_resend" and answer is None
    identities = a.native_ids(sample, row, got, c, a.lexical_reader())
    assert identities == [("grok_session", a.sha(session.encode())), ("grok_request", "a" * 64)]
    joined, records, seen = {}, [], set()
    entry = {"endpoint": "grok", "logical_sample_id": "logical", "request": row, "state": got["state"], "original_strict_native_verified": False}
    a.merge(joined, records, seen, entry, answer, identities)
    assert len(joined) == 1 and records == []
    with pytest.raises(ValueError, match="occupied twice"):
        a.merge(joined, records, seen, entry, None, identities)
    with pytest.raises(ValueError, match="Native identity"):
        a.merge(joined, records, seen, dict(entry, logical_sample_id="other"), None, identities)
    with pytest.raises(ValueError, match="cannot supply a vote"):
        a.merge({}, [], set(), dict(entry, state="semantic_rejected"), {"verdicts": []}, [])
    denied.assert_not_called()
    sol = tmp_path / "sol/0001-synthetic"
    thread = "a9b52b93-a2ea-4aa5-8c7b-4a20a016c3b3"
    sol_row = dict(row, endpoint="sol")
    write(sol / "native-identity.json", {"logical_sample_id": "logical", "session_id": None})
    receipt_path = sol / "native-receipts/codex-receipt.json"
    write(receipt_path, {"thread_id": thread, "turn_id": "turn-1"})
    receipt_pin = {"path": "native-receipts/codex-receipt.json", "sha256": a.sha(receipt_path.read_bytes()), "bytes": len(receipt_path.read_bytes())}
    write(sol / "native-result.json", {"provider_artifacts": {"codex_receipt": receipt_pin}, "reported": {"session_id": thread}})
    events = sol / "responses/batch-0001.attempt-0001.events.jsonl"
    events.parent.mkdir()
    events.write_bytes((json.dumps({"type": "thread.started", "thread_id": thread}) + "\n"
        + json.dumps({"type": "turn.completed", "usage": {"input_tokens": 1}}) + "\n").encode())
    sol_ids = a.native_ids(sol, sol_row, {"state": "accepted"}, c, a.lexical_reader())
    assert sol_ids == [("sol_thread", a.sha(thread.encode()))]
    sol_joined, sol_records = {}, []
    sol_entry = dict(entry, endpoint="sol", request=sol_row, state="accepted", original_strict_native_verified=True)
    a.merge(sol_joined, sol_records, set(), sol_entry, {"verdicts": []}, sol_ids)
    assert len(sol_joined) == len(sol_records) == 1
    events.write_bytes((json.dumps({"type": "thread.started", "thread_id": "abebd58b-3a32-40e8-86dd-1490362a5c1f"}) + "\n").encode())
    with pytest.raises(ValueError, match="Foreign native thread"):
        a.native_ids(sol, sol_row, {"state": "accepted"}, c, a.lexical_reader())
    write(receipt_path, {"thread_id": "malformed-thread", "turn_id": "turn-1"})
    receipt_pin.update(sha256=a.sha(receipt_path.read_bytes()), bytes=len(receipt_path.read_bytes()))
    write(sol / "native-result.json", {"provider_artifacts": {"codex_receipt": receipt_pin}, "reported": {"session_id": "malformed-thread"}})
    events.write_bytes((json.dumps({"type": "thread.started", "thread_id": "malformed-thread"}) + "\n").encode())
    with pytest.raises(ValueError):
        a.native_ids(sol, sol_row, {"state": "accepted"}, c, a.lexical_reader())
    old = SimpleNamespace(profile=Mock())
    monkeypatch.setattr(a, "predecessor", lambda: old)
    monkeypatch.setattr(a, "checked", lambda path, pin: b"code-only")
    monkeypatch.setattr(a, "build", denied)
    assert a.main(["--metadata-only"]) == 0
    assert json.loads(capsys.readouterr().out)["source_data_loaded"] is False
    with pytest.raises(ValueError, match="cannot touch"):
        a.main(["--metadata-only", "--config", str(tmp_path / "excluded-config")])
    denied.assert_not_called()
