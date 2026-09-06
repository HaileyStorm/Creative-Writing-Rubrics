"""Source-only prospective runtime checks; no native provider proof."""

from __future__ import annotations

import builtins
import hashlib
import importlib.util
import json
import socket
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "evaluation-results/hbq-human-alignment-dryad-full-hbq-analysis-v1/baseline_native_runtime.py"


def load():
    spec = importlib.util.spec_from_file_location("baseline_native_runtime_test", SOURCE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def binding(subject):
    return {"schema_version": 1, "evidence_class": "baseline_runtime_source_bindings", "baseline_plan_sha256": subject.PLAN_SHA256, "parent_protocol_sha256": subject.PROTOCOL_SHA256, "bridge_path": subject.BRIDGE, "bridge_sha256": "1" * 64, "shared_runtime_bindings": dict.fromkeys(subject.SHARED_PATHS, "2" * 64), "adapter_version": 4, "execution_policy": "bounded_nonvisual_deny_wins_attested", "tools": "deny_wins_none_attested"}


@pytest.mark.parametrize("change", [
    {"adapter_version": 3}, {"adapter_version": True}, {"tools": "none"},
    {"execution_policy": "bounded_nonvisual_read_only"}, {"baseline_plan_sha256": "0" * 64},
    {"shared_runtime_bindings": {"other.py": "2" * 64}},
])
def test_manifest_rejects_weaker_or_unrelated_bindings(change):
    subject = load()
    value = binding(subject)
    value.update(change)
    with pytest.raises(ValueError, match="manifest"):
        subject._manifest(json.dumps(value).encode())


def test_manifest_rejects_duplicate_and_nonfinite_fields():
    subject = load()
    with pytest.raises(ValueError, match="duplicate"):
        subject._manifest(b'{"schema_version":1,"schema_version":1}')
    with pytest.raises(ValueError, match="Nonfinite"):
        subject._manifest(b'{"schema_version":NaN}')


def test_actual_sources_load_without_provider_or_state_access(tmp_path, monkeypatch):
    subject = load()
    value = binding(subject)
    value["bridge_sha256"] = hashlib.sha256((ROOT / subject.BRIDGE).read_bytes()).hexdigest()
    value["shared_runtime_bindings"] = {name: hashlib.sha256((subject.SHARED / name).read_bytes()).hexdigest() for name in subject.SHARED_PATHS}
    path = tmp_path / "source-bindings.json"
    raw = json.dumps(value, sort_keys=True).encode()
    path.write_bytes(raw)
    original_read = Path.read_bytes
    original_build_class = builtins.__build_class__
    original_socket = socket.socket
    state_root = Path.home() / ".codex/state"

    def guarded_read(candidate):
        assert not candidate.resolve().is_relative_to(state_root), "runtime loader read account/provider state"
        return original_read(candidate)

    def guarded_class(function, name, *args, **kwargs):
        result = original_build_class(function, name, *args, **kwargs)
        if name == "Broker":
            result.__init__ = lambda *args, **kwargs: pytest.fail("runtime loader constructed Broker")
        return result

    class NoNetworkSocket(original_socket):
        def connect(self, *args, **kwargs):
            pytest.fail("runtime loader attempted network contact")

    monkeypatch.setattr(Path, "read_bytes", guarded_read)
    monkeypatch.setattr(builtins, "__build_class__", guarded_class)
    monkeypatch.setattr(socket, "socket", NoNetworkSocket)
    monkeypatch.setattr(socket, "create_connection", lambda *args, **kwargs: pytest.fail("network contact"))
    runtime = subject.load_runtime(path, expected_manifest_sha256=hashlib.sha256(raw).hexdigest())
    assert len(runtime.questions) == 178
    assert runtime.transport_sha256 == value["bridge_sha256"]
    assert runtime.provenance["provider_calls"] == 0
    assert runtime.provenance["native_admission"] is False
    assert runtime.provenance["execution_authority"] is False
    runtime.verify()
    path.write_bytes(raw + b" ")
    with pytest.raises(ValueError, match="changed"):
        runtime.verify()
