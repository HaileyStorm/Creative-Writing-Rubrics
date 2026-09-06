from __future__ import annotations

import importlib.util
import json
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
def terminal_inputs():
    terminal = load("dryad_terminal_residue", "terminal_residue.py")
    historical = load("dryad_historical_runtime_for_terminal", "historical_replay_runtime.py")
    runtime = historical.load_runtime()
    manifest = json.loads((RUN / "run.json").read_bytes())
    artifact = Path(manifest["configuration"]["artifact"]["path"])
    route = json.loads((SNAPSHOT / "cohorts/0003/route.json").read_bytes())
    return terminal, SimpleNamespace(**{**vars(runtime), "verify": lambda: None}), {"opaque_story_id": manifest["configuration"]["artifact_id"], "story_text": artifact.read_text(encoding="utf-8"), "artifact_path": str(artifact)}, {terminal.digest(terminal.canonical(route)): route}


def test_validator_authenticates_exact_residue_without_admitting_contact_28(terminal_inputs) -> None:
    terminal, runtime, source, routes = terminal_inputs
    proof = terminal.validate_terminal_residue(RUN, source=source, approved_routes=routes, runtime=runtime)
    assert proof["admitted_batches"] == 4 and proof["ordinal"] == 28
    assert proof["native_identity_claimed"] is False
    assert set(proof["residue_files"]) == set(terminal.RESIDUE)


@pytest.mark.parametrize("relative", [
    "responses/grok-broker/batch-0005-attempt-0001/context-bindings.json",
    "responses/grok-broker/batch-0005-attempt-0001/failure-receipt.json",
])
def test_validator_rejects_modified_context_or_residue_metadata(terminal_inputs, monkeypatch: pytest.MonkeyPatch, relative: str) -> None:
    terminal, runtime, source, routes = terminal_inputs
    target = RUN / relative
    original_read_bytes = Path.read_bytes

    def changed(path: Path) -> bytes:
        value = original_read_bytes(path)
        return value + b" " if path.resolve() == target.resolve() else value

    monkeypatch.setattr(Path, "read_bytes", changed)
    with pytest.raises(ValueError, match="Preserved terminal snapshot"):
        terminal.validate_terminal_residue(RUN, source=source, approved_routes=routes, runtime=runtime)


def test_validator_rejects_tree_dependency_and_run_link_drift(terminal_inputs, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    terminal, runtime, source, routes = terminal_inputs
    helper, helper_raw = terminal._helper()
    original_tree = helper._tree
    monkeypatch.setattr(helper, "_tree", lambda root: {**original_tree(root), "synthetic-extra.json": "0" * 64})
    monkeypatch.setattr(terminal, "_helper", lambda: (helper, helper_raw))
    with pytest.raises(ValueError, match="Preserved terminal snapshot"):
        terminal.validate_terminal_residue(RUN, source=source, approved_routes=routes, runtime=runtime)

    monkeypatch.undo()
    original_read_bytes = Path.read_bytes
    dependency = terminal.ROOT / "identity_exclusion.py"
    monkeypatch.setattr(Path, "read_bytes", lambda path: b"synthetic helper drift" if path.resolve() == dependency.resolve() else original_read_bytes(path))
    with pytest.raises(ValueError, match="helper source"):
        terminal.validate_terminal_residue(RUN, source=source, approved_routes=routes, runtime=runtime)

    monkeypatch.undo()
    link = tmp_path / "terminal-run-link"
    try:
        link.symlink_to(RUN, target_is_directory=True)
    except OSError:
        return
    with pytest.raises(ValueError, match="link or reparse"):
        terminal.validate_terminal_residue(link, source=source, approved_routes=routes, runtime=runtime)
