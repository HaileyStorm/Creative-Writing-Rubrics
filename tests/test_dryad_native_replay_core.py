from __future__ import annotations

import hashlib
import importlib.util
import json
import socket
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "evaluation-results" / "hbq-human-alignment-dryad-full-hbq-analysis-v1"
SNAPSHOT = Path.home() / "Documents/cwr-dryad-v2-contact28-reconcile-20260906-r1"
RUN = SNAPSHOT / "runs/size-0008/repetition-01/dryad-44cae24e55019e2cbf491660"


def load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, PACKAGE / filename)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def replay_inputs():
    historical = load("dryad_historical_runtime_for_replay", "historical_replay_runtime.py")
    runtime = historical.load_runtime()
    manifest = json.loads((RUN / "run.json").read_bytes())
    artifact = Path(manifest["configuration"]["artifact"]["path"])
    route = json.loads((SNAPSHOT / "cohorts/0003/route.json").read_bytes())
    terminal = load("dryad_terminal_for_replay", "terminal_residue.py")
    return {
        "runtime": SimpleNamespace(**{**vars(runtime), "verify": lambda: None}),
        "source": {"opaque_story_id": manifest["configuration"]["artifact_id"], "story_text": artifact.read_text(encoding="utf-8"), "artifact_path": str(artifact)},
        "routes": {terminal.digest(terminal.canonical(route)): route},
    }


def test_opted_terminal_replay_returns_only_four_identities_and_no_score(replay_inputs, monkeypatch: pytest.MonkeyPatch) -> None:
    core = load("dryad_native_replay_core", "native_replay_core.py")
    runtime = replay_inputs["runtime"]
    original_socket = socket.socket

    class NoNetworkSocket(original_socket):
        def connect(self, *args, **kwargs):
            pytest.fail("native replay must not contact a provider")

    monkeypatch.setattr(runtime.broker.Broker, "__init__", lambda *args, **kwargs: pytest.fail("native replay must not construct Broker"))
    monkeypatch.setattr(socket, "socket", NoNetworkSocket)
    monkeypatch.setattr(socket, "create_connection", lambda *args, **kwargs: pytest.fail("native replay must not open a connection"))
    before = {path.relative_to(SNAPSHOT): hashlib.sha256(path.read_bytes()).hexdigest() for path in SNAPSHOT.rglob("*") if path.is_file()}
    replay = core.admit_prefix(RUN, source=replay_inputs["source"], batch_size=8, approved_routes=replay_inputs["routes"],
                               expected_batches=4, runtime=runtime, terminal_residue=True)
    assert len(replay["native_identities"]) == 4 and replay["accepted_count"] == 32
    assert replay["score"] is None and replay["coverage"] is None
    assert replay["terminal_residue"]["ordinal"] == 28
    assert replay["terminal_residue"]["native_identity_claimed"] is False
    assert {path.relative_to(SNAPSHOT): hashlib.sha256(path.read_bytes()).hexdigest() for path in SNAPSHOT.rglob("*") if path.is_file()} == before


def test_original_prefix_rejects_terminal_residue_and_invalid_opt_in(replay_inputs) -> None:
    core = load("dryad_native_replay_core_ordinary", "native_replay_core.py")
    kwargs = {"run_root": RUN, "source": replay_inputs["source"], "approved_routes": replay_inputs["routes"], "runtime": replay_inputs["runtime"]}
    with pytest.raises(ValueError, match="rejected attempts|orphan evidence"):
        core.admit_prefix(batch_size=8, expected_batches=4, terminal_residue=False, **kwargs)
    with pytest.raises(ValueError, match="Terminal residue requires"):
        core.admit_prefix(batch_size=32, expected_batches=4, terminal_residue=True, **kwargs)
    with pytest.raises(ValueError, match="Terminal residue requires"):
        core.admit_prefix(batch_size=8, expected_batches=3, terminal_residue=True, **kwargs)
    with pytest.raises(ValueError, match="Terminal source binding"):
        core.admit_prefix(batch_size=8, expected_batches=4, terminal_residue=True,
                          **{**kwargs, "source": {**replay_inputs["source"], "story_text": "synthetic source drift"}})


def test_core_source_pin_drift_and_link_reject_without_source_writes(tmp_path: Path) -> None:
    core = load("dryad_native_replay_core_sources", "native_replay_core.py")
    source = tmp_path / "synthetic.py"
    raw = b"synthetic native source"
    source.write_bytes(raw)
    assert core._source(source, hashlib.sha256(raw).hexdigest()) == raw
    source.write_bytes(b"synthetic source drift")
    with pytest.raises(ValueError, match="source pin"):
        core._source(source, hashlib.sha256(raw).hexdigest())
    source.write_bytes(raw)
    link = tmp_path / "synthetic-link.py"
    try:
        link.symlink_to(source)
    except OSError:
        return
    with pytest.raises(ValueError, match="link or reparse"):
        core._source(link, hashlib.sha256(raw).hexdigest())
