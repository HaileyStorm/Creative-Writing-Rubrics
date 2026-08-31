from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from hbqrs.paths import book_root

ROOT = book_root() / "evaluation-results" / "cwr-guided-revision-gain-v2-live-exec-v8-crlf-replay-result-v1"
V7_TEST = book_root() / "tests" / "test_cwr_guided_revision_gain_v2_live_exec_v7_endpoint_continuation.py"


def mod():
    spec = importlib.util.spec_from_file_location("v8_crlf_replay", ROOT / "executor.py")
    assert spec and spec.loader
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def v7_fixture():
    spec = importlib.util.spec_from_file_location("v7_endpoint_fixture_for_v8", V7_TEST)
    assert spec and spec.loader
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    value._IMMUTABLE_CONTEXT = None
    value._VALIDATED_INPUTS = None
    return value


def _crlf_output(fixture, adapter, args, kwargs):
    completed = fixture._output(adapter, args, kwargs)
    assert completed.stdout.endswith(b"\n")
    return SimpleNamespace(returncode=0, stdout=completed.stdout[:-1] + b"\r\n")


def _prepared_crlf_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    package = mod()
    adapter = package._load_v7_adapter()
    adapter._test_real_inputs = adapter._inputs
    adapter._test_real_validated_inputs = adapter._validated_endpoint_inputs
    fixture = v7_fixture()
    run, rows = fixture._prepared(adapter, tmp_path, monkeypatch)
    monkeypatch.setattr(adapter, "_SUBPROCESS_RUN", lambda *args, **kwargs: _crlf_output(fixture, adapter, args, kwargs))
    results = adapter.execute_endpoint_wave(run_root=run, event_ids=[row["event_id"] for row in rows], allow_remote=True, queue_root=tmp_path / "queue")
    assert len(results) == 40 and all(row["state"] == "settled" for row in results)
    return package, run


def test_contract_is_provider_free_pinned_and_public() -> None:
    package = mod()
    assert package.contract()["mode"] == "provider_free_completed_v7_replay_only"
    source = (ROOT / "executor.py").read_text(encoding="utf-8")
    assert package.V7_SHA256 in source
    assert "C:\\\\Users" not in source
    assert "subprocess" not in source
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    for marker in ("hardcoded immutable V6", "e0f4181e4daed637b6c8e438e71b90129505bd2191202dd2ef43e0f7e406d172", "c139d7868f0226b2e507baa47c19f2b90adac1ee5ad7856bc12648972d7ae71a", "Off-host replay is **NO-GO**"):
        assert marker in readme


def test_crlf_full_wave_replays_and_projects_exact_geometry(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    package, run = _prepared_crlf_run(tmp_path, monkeypatch)
    monkeypatch.setattr(package, "EXPECTED_MEANS", {key: 0.0 for key in package.EXPECTED_MEANS})
    result = package.replay_completed_v7(source_root=run.resolve())
    assert result["provider_calls_made"] == 0
    assert len(result["underlying_endpoint_rows"]) == 40
    assert len(result["primary_guided_minus_control"]) == 16
    assert len(result["arm_minus_baseline"]) == 32
    assert all(row["adapter_stdout"]["bytes"] > 0 for row in result["underlying_endpoint_rows"])
    assert "C:\\" not in json.dumps(result, ensure_ascii=True)
    raw = next((run / "cells").glob("*/adapter-stdout.raw"))
    receipt = raw.parent / "verified-receipt.json"
    adapter = package._load_v7_adapter()
    replay_context = adapter._context()
    original = raw.read_bytes()
    binding = raw.parent / "adapter-stdout-binding.json"
    binding_original = binding.read_bytes()
    lf = original.rstrip(b"\r\n") + b"\n"
    lf_binding = json.loads(binding_original)
    lf_binding["raw_stdout"] = {"path": lf_binding["raw_stdout"]["path"], "bytes": len(lf), "sha256": adapter.sha(lf)}
    raw.write_bytes(lf)
    binding.write_bytes(adapter.canonical(lf_binding) + b"\n")
    replayed, _event = adapter._replay_receipt(run, receipt, context=replay_context)
    assert replayed["event_id"] == receipt.parent.name
    raw.write_bytes(original)
    binding.write_bytes(binding_original)
    for suffix in (b"", b"\r", b"\r\n\n"):
        raw.write_bytes(original.rstrip(b"\r\n") + suffix)
        with pytest.raises(ValueError, match="raw adapter"):
            adapter._replay_receipt(run, receipt, context=replay_context)
    raw.write_bytes(original)
    forged = json.loads(original)
    forged["result"]["output"]["overall"] = 7
    raw.write_bytes(json.dumps(forged, sort_keys=True).encode("ascii") + b"\r\n")
    with pytest.raises(ValueError, match="raw adapter"):
        adapter._replay_receipt(run, receipt, context=replay_context)
    raw.write_bytes(original)
    control = raw.parent / "adapter-control.json"
    control_raw = control.read_bytes()
    control.write_bytes(control_raw[:-1] + b"\r\n")
    with pytest.raises(ValueError, match="raw adapter"):
        adapter._replay_receipt(run, receipt, context=replay_context)
