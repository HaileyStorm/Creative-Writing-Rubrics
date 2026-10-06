"""Independent008 binding and terminal-missing replay boundary; no providers."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace
from threading import Event
from unittest.mock import Mock

import pytest

HERE = Path(__file__).resolve().parents[1] / "evaluation-results/hbq-matched-ttcw-20261004"
spec = importlib.util.spec_from_file_location("ttcw_suffix_v4_test", HERE / "collector_suffix_v4.py")
c = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c)


def test_low_disk_stops_actual_before_contact_callback_without_attempt_or_vote(tmp_path, monkeypatch):
    output = tmp_path / "results"; output.mkdir()
    c.record(output / "job.json", {"fixture": True})
    row = {"endpoint": "grok", "endpoint_ordinal": 323, "logical_sample_id": "a" * 64}
    binding = {"manifest_sha256": c.MANIFEST_SHA, "route": {"name": "synthetic"}, "route_sha256": "synthetic"}
    monkeypatch.setattr(c.base, "inputs", lambda *args: (b"prompt", b"{}", {}, {}))
    monkeypatch.setattr(c.shutil, "disk_usage", lambda path: SimpleNamespace(free=c.MINIMUM_FREE_DISK_BYTES - 1))
    contacted = Mock()

    def run_request(*args, **kwargs):
        kwargs["before_contact"]()
        contacted()
        raise AssertionError("Low-space request contacted provider")

    halt = Event()
    state = c.base.collect_one(row, binding, tmp_path, output, None, None, halt,
                             broker=SimpleNamespace(run_grok_native_request=run_request))
    sample = c.base.sample_path(output, row)
    terminal = c.base.json.loads((sample / "terminal.json").read_bytes())
    assert state == "unadmitted_no_resend" and halt.is_set()
    assert terminal["accepted"] is False and terminal["no_resend"] is True
    assert not (sample / "attempt-started.json").exists() and not (sample / "native-result.json").exists()
    contacted.assert_not_called()


def test_008_job_geometry_and_retained_failure_do_not_alias_007_or_require_answer(tmp_path, monkeypatch):
    route = {"model": "grok-4.7", "reasoning_effort": "high", "destination": "synthetic"}
    monkeypatch.setattr(c.base, "ROUTE_SHA", c.sha(c.canonical(route)))
    manifest = {"collection_policy": {"name": "semantic_reject_continue_v2", "collector_sha256": c.base.SOURCE_DRIVER_SHA},
        "continuation": {"reserved_through_endpoint_ordinal": 322, "source_manifest_sha256": c.SOURCE_MANIFEST_SHA,
            "prefix_jobs": [{"source_inventory_sha256": c.SOURCE_INVENTORY_SHA}]},
        "counts": {"requests_total": 1232}, "implementation": {"semantic_validator_sha256": "semantic", "schema_subset_sha256": "schema"},
        "artifacts": {}, "executor_contract": {"source_route_sha256": "source-route"}}
    binding = c.job_binding(manifest, "grok", 2, 2, route)
    assert binding["collector_policy"] == c.POLICY and binding["collector_sha256"] != c.NATIVE_BASE_SHA
    assert binding["manifest_sha256"] == c.MANIFEST_SHA and binding["reserved_through_endpoint_ordinal"] == 322
    assert (binding["first_endpoint_ordinal"], binding["last_endpoint_ordinal"], binding["selected_requests_per_endpoint"]) == (323, 1554, 1232)
    assert binding["native_base_collector_sha256"] == c.NATIVE_BASE_SHA
    assert not any(binding["owner_attestations"].values()) and binding["returned_allocation_natively_verified"] is False
    manifest["continuation"]["reserved_through_endpoint_ordinal"] = 279
    with pytest.raises(ValueError, match="geometry"):
        c.job_binding(manifest, "grok", 2, 2, route)
    manifest["continuation"]["reserved_through_endpoint_ordinal"] = 322
    with pytest.raises(ValueError, match="headroom"):
        c.job_binding(manifest, "grok", 3, 2, route)
    output = tmp_path / "results"; output.mkdir()
    c.record(output / "job.json", binding)
    row = {"endpoint": "grok", "endpoint_ordinal": 323, "logical_sample_id": "f" * 64}
    sample = c.base.sample_path(output, row); sample.mkdir()
    c.record(sample / "condition.json", row)
    condition = (sample / "condition.json").read_bytes()
    c.record(sample / "terminal.json", {"state": "unadmitted_no_resend", "accepted": False, "no_resend": True,
        "logical_sample_id": row["logical_sample_id"], "manifest_sha256": binding["manifest_sha256"],
        "job_sha256": c.sha((output / "job.json").read_bytes()), "retention_errors": [],
        "retained_artifacts": {"condition.json": {"sha256": c.sha(condition), "bytes": len(condition)}}})
    validator = SimpleNamespace(semantic_validate=Mock(side_effect=AssertionError("Missing vote must not be admitted")))
    terminal, answer = c.replay(sample, row, binding, tmp_path / "frozen", None, validator)
    assert terminal["state"] == "unadmitted_no_resend" and answer is None
    assert not (sample / "response.json").exists() and not (sample / "native-result.json").exists()
    validator.semantic_validate.assert_not_called()
    with pytest.raises(ValueError, match="008 replay"):
        c.replay(sample, dict(row, endpoint_ordinal=322), binding, tmp_path / "frozen", None, validator)
    with pytest.raises(ValueError, match="008 replay"):
        c.replay(sample, row, dict(binding, collector_policy="ttcw_untouched_suffix_execution_v3"), tmp_path / "frozen", None, validator)
    (sample / "condition.json").write_bytes(b"changed")
    with pytest.raises(ValueError):
        c.replay(sample, row, binding, tmp_path / "frozen", None, validator)
