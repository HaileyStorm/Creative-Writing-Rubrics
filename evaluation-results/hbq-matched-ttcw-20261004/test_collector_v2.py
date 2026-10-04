"""Invalid completed outputs count missing; uncertain contact still stops."""
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("ttcw_collector_v2_tests", HERE / "collector_v2.py")
collector = importlib.util.module_from_spec(spec)
spec.loader.exec_module(collector)
from test_collector import fixture_manifest, set_args


def fixtures(tmp_path):
    manifest, results, route = fixture_manifest(tmp_path)
    data = json.loads(manifest.read_bytes())
    context = b"Frozen synthetic context."
    (manifest.parent / "context.txt").write_bytes(context)
    data["artifacts"]["context.txt"] = {"sha256": collector.digest(context), "bytes": len(context)}
    data["collection_policy"] = {"name": collector.POLICY, "collector_sha256": collector.digest((HERE / "collector_v2.py").read_bytes())}
    data.pop("manifest_content_sha256")
    data["manifest_content_sha256"] = collector.digest(collector.canonical(data) + b"\n")
    manifest.write_bytes(collector.canonical(data) + b"\n")
    routes = json.loads((route / "routes.json").read_bytes())
    routes["routes"][0]["reported_model"] = "grok-4.7-build"
    (route / "routes.json").write_text(json.dumps(routes), encoding="utf-8")
    return manifest, results, route


def mock_provider(monkeypatch, *, failure=None):
    from model_work_queue import broker
    calls, envelopes = [], {}

    class Broker:
        def __init__(self, root):
            pass

        def run_grok_native_request(self, name, request, **options):
            options["before_contact"]()
            calls.append(options["session_id"])
            if failure == "ambiguity" and len(calls) == 2:
                return {"state": "ambiguous", "result": None}
            answer = {"reject": len(calls) == 1}
            session = options["session_id"]
            raw = collector.canonical({"structuredOutput": answer, "sessionId": session}) + b"\n"
            artifact = {"sha256": collector.digest(raw), "byte_length": len(raw)}
            envelopes[artifact["sha256"]] = raw
            return {"state": "completed", "result": {
                "output": answer, "output_hash": collector.digest(collector.canonical(answer)),
                "request_hash": collector.digest(collector.canonical(request)), "native_envelope_artifact": artifact,
                "runtime": {"session_id_hash": collector.digest(session.encode()), "requested_model": "grok-4.7",
                            "reported_model": "grok-4.7-build",
                            "execution_contract": {"output_schema_hash": collector.digest(collector.canonical(options["output_schema"]))}},
            }}

        def read_grok_native_envelope(self, artifact):
            return envelopes[artifact["sha256"]]

    def semantic(arm, answer, row, texts, subset, **options):
        if failure == "local":
            raise ValueError("Synthetic local admission failure")
        return {"accepted": not answer["reject"], "abstention": False,
                "errors": ["Synthetic quote mismatch"] if answer["reject"] else []}

    monkeypatch.setattr(broker, "Broker", Broker)
    monkeypatch.setattr(collector, "load_module", lambda *args: SimpleNamespace(semantic_validate=semantic))
    return calls


def test_semantic_rejection_continues_to_next_untouched_and_resume_never_resends(tmp_path, monkeypatch, capsys):
    manifest, results, route = fixtures(tmp_path)
    calls = mock_provider(monkeypatch)
    set_args(monkeypatch, manifest, results, route)
    assert collector.main() == 0
    assert len(calls) == 3
    folders = sorted(path for path in results.iterdir() if path.is_dir())
    terminals = [json.loads((path / "terminal.json").read_bytes()) for path in folders]
    assert [row["state"] for row in terminals] == ["semantic_rejected", "accepted", "accepted"]
    assert [row["accepted"] for row in terminals] == [False, True, True]
    saved = [(path / "terminal.json").read_bytes() for path in folders]
    job = json.loads((results / "job.json").read_bytes())
    assert job["collector_policy"] == collector.POLICY
    assert job["cutoff"] == "2026-10-16T05:40:00+00:00"
    assert job["automatic_retries"] == 0 and job["zero_charge_only"] is True
    progress = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert progress[-1]["semantic_rejected_this_invocation"] == 1
    assert progress[-1]["accepted_this_invocation"] == 2
    assert collector.main() == 0
    assert len(calls) == 3
    assert [(path / "terminal.json").read_bytes() for path in folders] == saved


@pytest.mark.parametrize("failure", ["ambiguity", "local", "expiry"])
def test_nonsemantic_failure_stops_untouched_suffix_and_blocks_resume(tmp_path, monkeypatch, failure):
    manifest, results, route = fixtures(tmp_path)
    calls = mock_provider(monkeypatch, failure=failure)
    if failure == "expiry":
        monkeypatch.setattr(collector, "CUTOFF", datetime(2020, 1, 1, tzinfo=timezone.utc))
    set_args(monkeypatch, manifest, results, route)
    assert collector.main() == 3
    assert len(calls) == (2 if failure == "ambiguity" else 1 if failure == "local" else 0)
    before = len(calls)
    with pytest.raises(ValueError, match="reconciliation; no resend"):
        collector.main()
    assert len(calls) == before
    assert not any(path.name.startswith("0003-") for path in results.iterdir())


def test_changed_rejection_receipt_blocks_resume_without_contact(tmp_path, monkeypatch):
    manifest, results, route = fixtures(tmp_path)
    calls = mock_provider(monkeypatch)
    set_args(monkeypatch, manifest, results, route, "--limit", "1")
    assert collector.main() == 0
    sample = next(path for path in results.iterdir() if path.is_dir())
    (sample / "acceptance.json").write_text(json.dumps({"accepted": True}), encoding="utf-8")
    with pytest.raises(ValueError, match="admission receipt differs"):
        collector.main()
    assert len(calls) == 1


def test_validate_only_has_no_provider_control_plane_or_output(tmp_path, monkeypatch):
    manifest, results, route = fixtures(tmp_path)
    from model_work_queue import broker
    def forbidden(*args, **options):
        raise AssertionError("No provider control plane in validation")
    monkeypatch.setattr(broker, "Broker", forbidden)
    set_args(monkeypatch, manifest, results, route, "--validate-only")
    assert collector.main() == 0
    assert not results.exists()


def test_changed_frozen_collector_policy_is_rejected_before_reservation(tmp_path, monkeypatch):
    manifest, results, route = fixtures(tmp_path)
    data = json.loads(manifest.read_bytes())
    data["collection_policy"]["collector_sha256"] = "0" * 64
    data.pop("manifest_content_sha256")
    data["manifest_content_sha256"] = collector.digest(collector.canonical(data) + b"\n")
    manifest.write_bytes(collector.canonical(data) + b"\n")
    calls = mock_provider(monkeypatch)
    set_args(monkeypatch, manifest, results, route)
    with pytest.raises(ValueError, match="collection policy"):
        collector.main()
    assert not results.exists() and not calls
