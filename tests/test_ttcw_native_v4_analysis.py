"""New native-v4 replay and owning-return boundaries; synthetic provider-free evidence."""
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
import uuid

import pytest

HERE = Path(__file__).resolve().parents[1] / "evaluation-results/hbq-matched-ttcw-20261004"
spec = importlib.util.spec_from_file_location("ttcw_native_v4_analysis_test", HERE / "analysis_chain_v4.py")
a = importlib.util.module_from_spec(spec)
spec.loader.exec_module(a)


def write(path, value):
    path.write_bytes(json.dumps(value, separators=(",", ":"), sort_keys=True).encode())


def test_v4_actual_job_failed_replay_and_reserved_identity(tmp_path, monkeypatch):
    chain, loaded = a.runtime()
    native, prior = loaded["suffix_v4"], loaded["analysis_v3"]
    root, output = tmp_path / "frozen", tmp_path / "results"
    root.mkdir(); output.mkdir()
    rows = [{"endpoint": "grok", "endpoint_ordinal": n, "logical_sample_id": f"{n:064x}",
             "prompt_sha256": "prompt", "schema_sha256": "schema", "request_sha256": f"request-{n}"}
            for n in range(1, 1555)]
    source = {"requests": rows[322:], "counts": {"requests_total": 1232}, "artifacts": {},
        "collection_policy": {"name": "synthetic"}, "implementation": {"semantic_validator_sha256": "semantic", "schema_subset_sha256": "schema"},
        "executor_contract": {"source_route_sha256": "source-route"},
        "continuation": {"reserved_through_endpoint_ordinal": 322, "source_manifest_sha256": "source",
                         "prefix_jobs": [{"source_inventory_sha256": "inventory"}]}}
    path = root / "manifest.json"; write(path, source)
    monkeypatch.setattr(native, "MANIFEST_SHA", prior.sha(path.read_bytes()))
    route = {"model": "grok-4.7", "reasoning_effort": "high", "destination": "synthetic"}
    monkeypatch.setattr(native.base, "ROUTE_SHA", native.sha(native.canonical(route)))
    true = dict.fromkeys(a.ATTESTATIONS, True)
    job = native.job_binding(source, "grok", 2, 2, route, owner_attestations=true)
    assert job["selected_requests_per_endpoint"] == 1232 and job["original_requests_total"] == 3108
    assert job["own_lifecycle_binding_verified"] is False
    write(output / "job.json", job)
    monkeypatch.setattr(native, "load_manifest", lambda *args: (source, root, rows[322:], None, None))
    monkeypatch.setattr(loaded["analysis"], "validate_continuation", lambda *args, **kwargs: None)
    row = rows[322]; sample = native.base.sample_path(output, row); sample.mkdir()
    session = str(uuid.uuid4())
    write(sample / "condition.json", row)
    write(sample / "native-identity.json", {"session_id": session, "logical_sample_id": row["logical_sample_id"]})
    write(sample / "attempt-started.json", {"attempt": 1, "no_resend": True, "state": "before_contact", "time": "2026-10-06T04:00:00+00:00",
        "session_id": session, "logical_sample_id": row["logical_sample_id"], "job_sha256": prior.sha((output / "job.json").read_bytes()),
        "manifest_sha256": native.MANIFEST_SHA, "prompt_sha256": "prompt", "schema_sha256": "schema"})
    # The excluded answer has an invalid JSON escape. Metadata projection must not decode it.
    (sample / "native-result.json").write_bytes(b'{"state":"completed","result":{"runtime":{"request_id_hash":"failed-native-request"},"output":"\\q"}}')
    write(sample / "terminal.json", {"state": "unadmitted_no_resend", "accepted": False, "no_resend": True,
        "logical_sample_id": row["logical_sample_id"], "manifest_sha256": native.MANIFEST_SHA,
        "job_sha256": prior.sha((output / "job.json").read_bytes()), "retention_errors": [],
        "retained_artifacts": {p.name: {"sha256": prior.sha(p.read_bytes()), "bytes": p.stat().st_size} for p in sample.iterdir()}})
    specification = {"endpoint": "grok", "collector_policy": a.COLLECTOR_POLICY, "manifest_path": str(path),
        "manifest_sha256": native.MANIFEST_SHA, "results_root": str(output), "job_sha256": prior.sha((output / "job.json").read_bytes())}
    _, records, identities, public = chain.replay_source(specification, {"requests": rows}, b"base", {}, None, loaded, None, 0)
    assert public["states"] == {"unadmitted_no_resend": 1}
    assert records[("grok", row["logical_sample_id"])]["accepted"] is None
    assert ("grok_request", "failed-native-request") in identities and len(identities) == 2
    joined = chain.merge([records], {("grok", r["logical_sample_id"]): r for r in rows})
    assert len(joined) == 1554 and sum(r["state"] == "not_collected" for r in joined.values()) == 1553
    with pytest.raises(ValueError, match="Duplicate attempted"):
        chain.merge([records, records], {("grok", r["logical_sample_id"]): r for r in rows})
    job["owner_attestations"][a.ATTESTATIONS[0]] = False; write(output / "job.json", job)
    specification["job_sha256"] = prior.sha((output / "job.json").read_bytes())
    with pytest.raises(ValueError, match="four actual"):
        chain.replay_source(specification, {"requests": rows}, b"base", {}, None, loaded, None, 0)
    with pytest.raises(ValueError, match="Unknown source"):
        chain.replay_source(dict(specification, collector_policy="future_unreviewed"), {}, b"", {}, None, loaded, None, 0)


def test_each_v4_own_return_and_full_terminal_gate_before_labels(tmp_path, monkeypatch):
    chain, loaded = a.runtime(); prior = loaded["analysis_v3"]
    loaded["analysis"].load_labels = Mock(side_effect=AssertionError("labels closed"))
    output, life = tmp_path / "results", tmp_path / "life"; output.mkdir(); life.mkdir()
    job = {"collector_policy": a.COLLECTOR_POLICY, "collector_sha256": a.COLLECTOR_SHA, "owner_attestations": dict.fromkeys(a.ATTESTATIONS, True),
        "endpoint": "grok", "manifest_sha256": "manifest", "route_sha256": "route", "workers": 2, "owner_declared_endpoint_headroom": 2}
    write(output / "job.json", job)
    launcher = life / "launcher.py"; launcher.write_text("# synthetic owning launcher\n")
    argv = ["python", "-B", str(HERE / "collector_suffix_v4.py"), "--manifest", str(tmp_path / "manifest.json"),
        "--manifest-sha256", "manifest", "--results-dir", str(output), "--endpoint", "grok", "--workers", "2", "--endpoint-headroom", "2",
        "--route-sha256", "route", "--route-root", str(loaded["suffix_v4"].TOOLS.parent / "state/model-work-queue-cwr-placeholder-r31"), *a.FLAGS]
    invocation = {"argv": argv, "time": "2026-10-06T00:00:00+00:00", "launcher_sha256": prior.sha(launcher.read_bytes()),
        "collector_sha256": a.COLLECTOR_SHA, "manifest_sha256": "manifest", "route_sha256": "route", "workers": 2, "no_resend": True}
    write(life / "invocation.json", invocation); invsha = prior.sha((life / "invocation.json").read_bytes())
    write(life / "run-started.json", {"argv": argv, "time": "2026-10-06T00:01:00+00:00", "no_resend": True,
        "invocation_sha256": invsha, "launcher_sha256": invocation["launcher_sha256"]})
    write(life / "native-handle.json", {"argv": argv, "pid": 2, "no_resend": True, "cwd": str(HERE.parents[1])})
    write(life / "handle.json", {"argv": [str(HERE.parents[1] / ".venv/Scripts/python.exe"), "-B", str(launcher.resolve()), "--run", "--invocation-sha256", invsha],
        "pid": 1, "workers": 2, "no_resend": True, "cwd": str(HERE.parents[1]), "native_job": str(output / "job.json"), "lifecycle": str(life)})
    write(life / "terminal.json", {"exit_code": 3, "native_exit_confirmed": True, "no_resend": True,
        "time": "2026-10-06T00:02:00+00:00", "invocation_sha256": invsha})
    names = {"invocation": "invocation.json", "outer_terminal": "terminal.json", "run_started": "run-started.json",
             "native_handle": "native-handle.json", "handle": "handle.json", "launcher": "launcher.py"}
    specification = {"endpoint": "grok", "collector_policy": a.COLLECTOR_POLICY, "manifest_path": str(tmp_path / "manifest.json"),
        "manifest_sha256": "manifest", "results_root": str(output), "job_sha256": prior.sha((output / "job.json").read_bytes()),
        "lifecycle": {k: {"path": str(life / v), "sha256": prior.sha((life / v).read_bytes())} for k, v in names.items()}}
    assert prior.verify_lifecycle(specification)[0]["execution_attestations_verified"] is True
    wrapper = json.loads((life / "handle.json").read_bytes())
    wrapper["argv"][-1] = "0" * 64; write(life / "handle.json", wrapper)
    specification["lifecycle"]["handle"]["sha256"] = prior.sha((life / "handle.json").read_bytes())
    with pytest.raises(ValueError, match="owning wrapper"):
        prior.verify_lifecycle(specification)
    wrapper["argv"][-1] = invsha; write(life / "handle.json", wrapper)
    specification["lifecycle"]["handle"]["sha256"] = prior.sha((life / "handle.json").read_bytes())
    joined = {n: {"state": "definitely_not_contacted", "accepted": None, "source_index": 0, "request": {
        "endpoint_ordinal": n + 1, "logical_sample_id": str(n)}} for n in range(3108)}
    release = Mock(); monkeypatch.setattr(chain, "release_labels", release)
    with pytest.raises(ValueError, match="Explicit"):
        a.release_labels({"sources": [specification]}, {}, joined, {}, {}, loaded, chain, tmp_path / "labels")
    with pytest.raises(ValueError, match="Both own endpoint"):
        a.release_labels({"sources": [specification]}, {}, joined, {}, {}, loaded, chain, tmp_path / "labels", explicit_release=True)
    joined[0]["state"] = "not_collected"
    with pytest.raises(ValueError, match="every original planned"):
        a.release_labels({"sources": [specification]}, {}, joined, {}, {}, loaded, chain, tmp_path / "labels", explicit_release=True)
    outer = json.loads((life / "terminal.json").read_bytes()); outer["native_exit_confirmed"] = False; write(life / "terminal.json", outer)
    specification["lifecycle"]["outer_terminal"]["sha256"] = prior.sha((life / "terminal.json").read_bytes())
    with pytest.raises(ValueError, match="Own true outer"):
        prior.verify_lifecycle(specification)
    release.assert_not_called(); loaded["analysis"].load_labels.assert_not_called()
