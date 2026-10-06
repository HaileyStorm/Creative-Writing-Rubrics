"""Synthetic009 own-return and denominator boundaries, without native contacts."""
import importlib.util
import json
from pathlib import Path
from unittest.mock import Mock
import uuid

import pytest

HERE = Path(__file__).resolve().parents[1] / "evaluation-results/hbq-matched-ttcw-20261004"
spec = importlib.util.spec_from_file_location("ttcw_native_v5_analysis_test", HERE / "analysis_chain_v5.py")
a = importlib.util.module_from_spec(spec)
spec.loader.exec_module(a)


def save(path, value, prior):
    path.write_bytes(json.dumps(value, sort_keys=True).encode())
    return {"path": str(path), "sha256": prior.sha(path.read_bytes())}


def returned_fixture(tmp_path, loaded):
    prior, native = loaded["analysis_v3"], loaded["suffix_v5"]
    life, results = tmp_path / "own-life", tmp_path / "own-results"
    life.mkdir(); results.mkdir()
    launcher = tmp_path / "launcher.py"
    launcher.write_text("# synthetic owning wrapper\n")
    attestations = {key: True for key in loaded["analysis_v4"].ATTESTATIONS}
    job = {"endpoint": "grok", "collector_policy": a.COLLECTOR_POLICY, "collector_sha256": a.COLLECTOR_SHA,
           "manifest_sha256": a.MANIFEST_SHA, "route_sha256": "route", "workers": 2,
           "owner_declared_endpoint_headroom": 2, "owner_attestations": attestations,
           "own_lifecycle_binding_verified": True, "owner_lifecycle_root": str(life)}
    manifest = tmp_path / "manifest.json"
    argv = [str(HERE.parents[1] / ".venv/Scripts/python.exe"), "-B", str(HERE / "collector_suffix_v5.py"),
        "--manifest", str(manifest), "--manifest-sha256", a.MANIFEST_SHA, "--results-dir", str(results),
        "--workers", "2", "--endpoint-headroom", "2", "--route-sha256", "route", "--route-root",
        str(native.TOOLS.parent / "state/model-work-queue-cwr-placeholder-r31"),
        "--owner-lifecycle-root", str(life), *loaded["analysis_v4"].FLAGS]
    inv = {"argv": argv, "owner": a.OWNER, "owner_attestations": attestations,
        "time": "2026-10-06T07:00:00Z", "launcher_sha256": prior.sha(launcher.read_bytes()),
        "collector_sha256": a.COLLECTOR_SHA, "manifest_sha256": a.MANIFEST_SHA,
        "route_sha256": "route", "workers": 2, "no_resend": True}
    pins = {"invocation": save(life / "invocation.json", inv, prior)}
    inv_sha = pins["invocation"]["sha256"]
    job["owner_lifecycle_invocation_sha256"] = inv_sha
    job_pin = save(results / "job.json", job, prior)
    pins["launcher"] = {"path": str(launcher), "sha256": inv["launcher_sha256"]}
    pins["run_started"] = save(life / "run-started.json", {"argv": argv,
        "time": "2026-10-06T07:00:02Z", "launcher_sha256": inv["launcher_sha256"],
        "invocation_sha256": inv_sha, "no_resend": True}, prior)
    common = {"cwd": str(HERE.parents[1]), "no_resend": True,
              "creation_time_basis": "Windows GetProcessTimes on owned Popen handle"}
    pins["native_handle"] = save(life / "native-handle.json", dict(common, argv=argv, pid=2,
        process_creation_utc="2026-10-06T07:00:03Z"), prior)
    pins["handle"] = save(life / "handle.json", dict(common, pid=1, workers=2,
        argv=[argv[0], "-B", str(launcher), "--run", "--invocation-sha256", inv_sha],
        native_job=str(results / "job.json"), lifecycle=str(life),
        process_creation_utc="2026-10-06T07:00:01Z"), prior)
    pins["outer_terminal"] = save(life / "terminal.json", {"exit_code": 3, "no_resend": True,
        "native_exit_confirmed": True, "invocation_sha256": inv_sha, "time": "2026-10-06T07:00:05Z"}, prior)
    dispatch = {"policy": a.COLLECTOR_POLICY, "job_sha256": job_pin["sha256"],
        "owner_lifecycle_invocation_sha256": inv_sha, "workers": 2, "inflight_at_terminal": 0,
        "automatic_retries": 0, "human_release_eligible": False, "stopped": True,
        "states": [{"ordinal": 338, "state": "ambiguous"}]}
    pins["dispatch_terminal"] = save(results / "dispatch-terminal.json", dispatch, prior)
    source = {"endpoint": "grok", "collector_policy": a.COLLECTOR_POLICY,
        "manifest_path": str(manifest), "manifest_sha256": a.MANIFEST_SHA,
        "results_root": str(results), "job_sha256": job_pin["sha256"], "lifecycle": pins}
    return source, job, dispatch


def test_009_actual_own_invocation_and_joined_dispatch_are_required(tmp_path, monkeypatch):
    chain, loaded = a.runtime()
    prior = loaded["analysis_v3"]
    source, job, dispatch = returned_fixture(tmp_path, loaded)
    proof, _, _ = prior.verify_lifecycle(source)
    assert proof["native_dispatcher_terminal_receipt"] and proof["code_backed_joined_local_drain"]
    assert proof["inflight_zero_natively_measured"] is False
    assert proof["physical_remote_settlement_proven"] is False
    assert "--endpoint" not in json.loads(Path(source["lifecycle"]["invocation"]["path"]).read_bytes())["argv"]
    native = loaded["suffix_v5"]
    rows = [{"endpoint": "grok", "endpoint_ordinal": n, "logical_sample_id": f"{n:064x}",
        "prompt_sha256": "prompt", "schema_sha256": "schema"} for n in range(1, 1555)]
    manifest = {"requests": rows[337:], "continuation": {"reserved_through_endpoint_ordinal": 337}}
    manifest_pin = save(Path(source["manifest_path"]), manifest, prior)
    source["manifest_sha256"] = manifest_pin["sha256"]
    job.update(manifest_sha256=manifest_pin["sha256"], route={}, reserved_through_endpoint_ordinal=337)
    source["job_sha256"] = save(Path(source["results_root"]) / "job.json", job, prior)["sha256"]
    dispatch["job_sha256"] = source["job_sha256"]
    source["lifecycle"]["dispatch_terminal"] = save(Path(source["results_root"]) / "dispatch-terminal.json", dispatch, prior)
    row = rows[337]
    sample = native.native.sample_path(Path(source["results_root"]), row)
    sample.mkdir()
    save(sample / "condition.json", row, prior)
    session = str(uuid.uuid4())
    save(sample / "native-identity.json", {"session_id": session, "logical_sample_id": row["logical_sample_id"]}, prior)
    save(sample / "attempt-started.json", {"session_id": session, "logical_sample_id": row["logical_sample_id"],
        "job_sha256": source["job_sha256"], "manifest_sha256": source["manifest_sha256"],
        "prompt_sha256": "prompt", "schema_sha256": "schema", "no_resend": True,
        "state": "before_contact", "attempt": 1, "time": "2026-10-06T07:00:04Z"}, prior)
    (sample / "native-result.json").write_bytes(b'{"result":{"runtime":{"request_id_hash":"own-request"},"output":"\\q"}}')
    retained = {p.name: {"sha256": prior.sha(p.read_bytes()), "bytes": p.stat().st_size} for p in sample.iterdir()}
    save(sample / "terminal.json", {"state": "ambiguous", "accepted": False, "no_resend": True,
        "job_sha256": source["job_sha256"], "manifest_sha256": source["manifest_sha256"],
        "logical_sample_id": row["logical_sample_id"], "retained_artifacts": retained, "retention_errors": []}, prior)
    monkeypatch.setattr(native, "MANIFEST_SHA", source["manifest_sha256"])
    monkeypatch.setattr(native, "load_manifest", Mock(return_value=(manifest, tmp_path, rows[337:], None, None)))
    bind = Mock(return_value=job)
    monkeypatch.setattr(native, "job_binding", bind)
    monkeypatch.setattr(loaded["analysis"], "validate_continuation", Mock())
    no_inputs = Mock(side_effect=AssertionError("failed observation opened source"))
    monkeypatch.setattr(native.native, "inputs", no_inputs)
    result = a.replay_v5(source, {"requests": rows}, b"original", {}, None, loaded, None, 0,
                         prior=prior, previous=loaded["analysis_v4"])
    assert next(iter(result[1].values()))["accepted"] is None
    assert ("grok_request", "own-request") in result[2]
    bind.assert_called_once_with(manifest, 2, 2, {}, job["owner_attestations"], source["lifecycle"]["invocation"]["sha256"])
    no_inputs.assert_not_called()
    dispatch["states"].append(dispatch["states"][0])
    source["lifecycle"]["dispatch_terminal"] = save(Path(source["results_root"]) / "dispatch-terminal.json", dispatch, prior)
    with pytest.raises(ValueError, match="foreign/duplicate"):
        a.dispatch_receipt(source, job, prior)
    source["lifecycle"]["outer_terminal"]["path"] = str(tmp_path / "absent-return.json")
    job_reader = Mock(side_effect=AssertionError("job opened before outer"))
    original = prior.checked
    prior.checked = lambda path, pin: job_reader() if Path(path).name == "job.json" else original(path, pin)
    with pytest.raises(FileNotFoundError):
        a.build({"sources": [source]}, (chain, loaded))
    job_reader.assert_not_called()


def test_original_denominator_and_explicit_release_remain_closed(tmp_path):
    chain, loaded = a.runtime()
    source, _, _ = returned_fixture(tmp_path, loaded)
    # A retained ambiguous observation supplies no vote;1217 suffix planning is not3108 terminal evidence.
    joined = {n: {"state": "ambiguous", "accepted": None, "terminal_evidence_verified": True,
        "source_index": 0, "request": {"endpoint_ordinal": n, "logical_sample_id": f"{n:064x}"}}
        for n in range(1, 3109)}
    labels = Mock(side_effect=AssertionError("labels opened"))
    chain.release_labels = labels
    args = ({"sources": [source]}, {}, joined, {}, {}, loaded, chain, tmp_path / "sealed-labels.json")
    with pytest.raises(ValueError, match="Explicit postprediction"):
        a.release_labels(*args)
    joined[3108]["state"] = "not_collected"
    with pytest.raises(ValueError, match="every original planned slot"):
        a.release_labels(*args, explicit_release=True)
    joined[3108]["state"] = "definitely_not_contacted"
    with pytest.raises(ValueError, match="Precontact missing"):
        a.release_labels(*args, explicit_release=True)
    joined[3108]["state"] = "ambiguous"
    with pytest.raises(ValueError, match="009 unstarted"):
        a.release_labels(*args, explicit_release=True)
    labels.assert_not_called()
    project = loaded["project_json"]
    raw = b'{"state":"completed","result":{"runtime":{"request_id_hash":"own-request"},"output":"\\q"}}'
    assert loaded["analysis_v4"].native_identity_metadata(raw, project)["result"]["runtime"]["request_id_hash"] == "own-request"
