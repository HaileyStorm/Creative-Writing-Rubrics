from __future__ import annotations

import builtins
import hashlib
import importlib.util
import socket
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "evaluation-results" / "hbq-human-alignment-dryad-full-hbq-analysis-v1"
SOURCE = PACKAGE / "historical_replay_runtime.py"


def load():
    spec = importlib.util.spec_from_file_location("dryad_historical_replay_runtime", SOURCE)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_installed_loader_reads_only_pinned_sources_without_runtime_authority(monkeypatch: pytest.MonkeyPatch) -> None:
    subject = load()
    original_read_bytes = Path.read_bytes
    original_build_class = builtins.__build_class__
    original_socket = socket.socket
    reads: list[Path] = []
    state_root = (Path.home() / ".codex" / "state").resolve()
    allowed_state = {
        subject.MANIFEST.resolve(),
        (subject.ROLLBACK / "broker.py").resolve(),
        (subject.ROLLBACK / "adapters/grok_exec.py").resolve(),
    }

    def guarded_read(path: Path) -> bytes:
        resolved = path.resolve()
        if resolved.is_relative_to(state_root):
            assert resolved in allowed_state
        reads.append(resolved)
        return original_read_bytes(path)

    def guarded_class(function, name, *args, **kwargs):
        value = original_build_class(function, name, *args, **kwargs)
        if name == "Broker":
            value.__init__ = lambda *args, **kwargs: pytest.fail("historical loader must not construct Broker")
        return value

    class NoNetworkSocket(original_socket):
        def connect(self, *args, **kwargs):
            pytest.fail("historical loader must not connect to a provider")

    def no_connection(*args, **kwargs):
        pytest.fail("historical loader must not open a provider connection")

    monkeypatch.setattr(Path, "read_bytes", guarded_read)
    monkeypatch.setattr(builtins, "__build_class__", guarded_class)
    monkeypatch.setattr(socket, "socket", NoNetworkSocket)
    monkeypatch.setattr(socket, "create_connection", no_connection)
    runtime = subject.load_runtime()

    assert len(runtime.questions) == 178
    assert runtime.provenance["evidence_class"] == "historical_v2_runtime_loader_only"
    assert runtime.provenance["provider_calls"] == 0
    assert runtime.provenance["native_admission"] is False
    assert runtime.provenance["execution_authority"] is False
    assert set(runtime.provenance["storage_map"]) == {
        "adapters.json_schema_subset", "image_canary", "grok_usage_evidence",
        "prepare_grok_evidence", "broker", "adapters.grok_exec",
    }
    assert allowed_state <= set(reads)
    assert all(not path.is_relative_to(state_root) or path in allowed_state for path in reads)
    runtime.verify()


def test_synthetic_source_capture_rejects_drift_link_and_reparse_ancestry(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    subject = load()
    source = tmp_path / "synthetic.py"
    raw = b"synthetic frozen source"
    source.write_bytes(raw)
    captures: dict[Path, bytes] = {}
    assert subject._read(source, hashlib.sha256(raw).hexdigest(), captures) == raw
    assert captures == {source.resolve(): raw}

    source.write_bytes(b"synthetic source drift")
    with pytest.raises(ValueError, match="source pin"):
        subject._read(source, hashlib.sha256(raw).hexdigest(), {})

    source.write_bytes(raw)
    original_lstat = Path.lstat

    def reparse(path: Path):
        info = original_lstat(path)
        if path == tmp_path:
            return SimpleNamespace(st_mode=info.st_mode, st_file_attributes=0x400)
        return info

    monkeypatch.setattr(Path, "lstat", reparse)
    with pytest.raises(ValueError, match="link or reparse"):
        subject._read(source, hashlib.sha256(raw).hexdigest(), {})

    monkeypatch.setattr(Path, "lstat", original_lstat)
    link = tmp_path / "synthetic-link.py"
    try:
        link.symlink_to(source)
    except OSError:
        return
    with pytest.raises(ValueError, match="link or reparse"):
        subject._read(link, hashlib.sha256(raw).hexdigest(), {})
