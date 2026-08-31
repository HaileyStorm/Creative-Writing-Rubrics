from __future__ import annotations

import importlib.util
import json
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "evaluation-results" / "hbq-human-alignment-optimizer-v5-f20-descendant13-nextwave-grok-reconcile-v2-existing-output"
LIVE = Path(r"C:\Users\Haile\Documents\cwr-hanna-desc13-grok-wave-f7ac506-20260831a")


def module():
    spec = importlib.util.spec_from_file_location("_desc13_recovery_v2", PACKAGE / "recover.py")
    assert spec and spec.loader
    value = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = value
    spec.loader.exec_module(value)
    return value


def shaped_copy(tmp_path: Path) -> Path:
    source = tmp_path / "immutable-live-shaped-copy"
    shutil.copytree(LIVE, source)
    return source


def fingerprint(root: Path) -> dict[str, bytes]:
    return {str(path.relative_to(root)): path.read_bytes() for path in root.rglob("*") if path.is_file()}


def test_actual_live_shaped_copy_recovers_all_ten_without_provider_or_source_mutation(tmp_path: Path):
    value = module(); source = shaped_copy(tmp_path); before = fingerprint(source)
    result = value.recover(source_root=source, target_root=tmp_path / "recovery")
    assert fingerprint(source) == before
    assert result["classification_counts"] == {
        "rejected_invalid_profile_proposals": 10,
        "profile_geometry_drift": 7,
        "profile_factors_drift": 3,
    }
    assert result["provider_calls_made"] == result["process_launches"] == 0
    assert result["original_process_launches_per_cell"] == 1
    assert result["original_provider_calls_made_per_cell"] == "unknown"
    assert result["process_launches_scope"] == "provider_or_executor_only; local Git provenance subprocesses are excluded"
    assert result["native_endpoint_contact_cardinality"] == "unproven_not_reconstructed"
    cells = result["cells"]
    assert len(cells) == 10
    assert len({cell["envelope_request_id"] for cell in cells}) == len({cell["envelope_session_id"] for cell in cells}) == 10
    assert all(cell["status"] == "rejected_invalid_profile_proposal" for cell in cells)
    assert all(set(cell["proposal"]) == {"instruction", "change_summary", "instruction_sha256", "profile_sha256"} for cell in cells)
    manifest = json.loads((tmp_path / "recovery" / "recovery-manifest.json").read_text(encoding="utf-8"))
    assert manifest == result


def test_coherent_substituted_proposal_envelope_rejects_on_exact_source_pin(tmp_path: Path):
    value = module(); source = shaped_copy(tmp_path)
    path = source / "descendant13-nextwave-01-scale-adjacency" / "responses" / "batch-0001.attempt-0001.grok.envelope.json"
    envelope = json.loads(path.read_text(encoding="utf-8"))
    proposal = envelope["structuredOutput"]
    proposal["instruction"] += " Coherently substituted."
    envelope["text"] = json.dumps(proposal, separators=(",", ":"))
    path.write_text(json.dumps(envelope), encoding="utf-8")
    with pytest.raises(ValueError, match="source pin"):
        value.recover(source_root=source, target_root=tmp_path / "recovery")


def test_reported_grok_build_one_call_model_usage_is_bound(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    value = module(); source = shaped_copy(tmp_path)
    cell_id = "descendant13-nextwave-01-scale-adjacency"
    path = source / cell_id / "responses" / "batch-0001.attempt-0001.grok.envelope.json"
    envelope = json.loads(path.read_text(encoding="utf-8")); envelope["modelUsage"]["grok-4.6-build"]["modelCalls"] = 2
    path.write_text(json.dumps(envelope), encoding="utf-8")
    monkeypatch.setitem(value.EXPECTED_ENVELOPE_SHA256, cell_id, value.sha256(path.read_bytes()))
    with pytest.raises(ValueError, match="model usage shape"):
        value.recover(source_root=source, target_root=tmp_path / "recovery")


@pytest.mark.parametrize("relative", [
    "catalog.json",
    "descendant13-nextwave-01-scale-adjacency/prompt-request.bin",
    "descendant13-nextwave-02-speaker-attribution/responses/batch-0001.attempt-0001.grok.envelope.json",
])
def test_source_tamper_rejects_before_target_write(tmp_path: Path, relative: str):
    value = module(); source = shaped_copy(tmp_path); path = source / relative
    if path.name.endswith(".json"):
        envelope = json.loads(path.read_text(encoding="utf-8")); envelope["stopReason"] = "tampered"; path.write_text(json.dumps(envelope), encoding="utf-8")
    else:
        path.write_bytes(path.read_bytes() + b" ")
    target = tmp_path / "recovery"
    with pytest.raises(ValueError):
        value.recover(source_root=source, target_root=target)
    assert not target.exists()


def test_duplicate_envelope_session_and_terminal_tamper_reject(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    value = module(); source = shaped_copy(tmp_path)
    first = source / "descendant13-nextwave-01-scale-adjacency" / "responses" / "batch-0001.attempt-0001.grok.envelope.json"
    second = source / "descendant13-nextwave-02-speaker-attribution" / "responses" / "batch-0001.attempt-0001.grok.envelope.json"
    first_value = json.loads(first.read_text(encoding="utf-8")); second_value = json.loads(second.read_text(encoding="utf-8"))
    second_value["sessionId"] = first_value["sessionId"]
    second.write_text(json.dumps(second_value), encoding="utf-8")
    monkeypatch.setitem(value.EXPECTED_ENVELOPE_SHA256, "descendant13-nextwave-02-speaker-attribution", value.sha256(second.read_bytes()))
    with pytest.raises(ValueError, match="duplicate or absent"):
        value.recover(source_root=source, target_root=tmp_path / "duplicate")
    source = shaped_copy(tmp_path / "terminal")
    path = source / "descendant13-nextwave-01-scale-adjacency" / "result.json"
    terminal = json.loads(path.read_text(encoding="utf-8")); terminal["process_launches"] = 0
    path.write_text(json.dumps(terminal), encoding="utf-8")
    with pytest.raises(ValueError, match="terminal result"):
        value.recover(source_root=source, target_root=tmp_path / "terminal-result")


def test_preexisting_target_and_unsafe_extra_source_artifact_reject(tmp_path: Path):
    value = module(); source = shaped_copy(tmp_path); target = tmp_path / "exists"; target.mkdir()
    with pytest.raises(ValueError, match="fresh disjoint"):
        value.recover(source_root=source, target_root=target)
    source = shaped_copy(tmp_path / "extra")
    (source / "descendant13-nextwave-01-scale-adjacency" / "unexpected.txt").write_text("no", encoding="utf-8")
    with pytest.raises(ValueError, match="inventory"):
        value.recover(source_root=source, target_root=tmp_path / "extra-target")


def test_package_has_no_execution_or_provider_surface():
    source = (PACKAGE / "recover.py").read_text(encoding="utf-8").lower()
    for forbidden in ("allow_remote", "runner", "queue", "requests", "urllib", "http", "dspy", "optuna"):
        assert forbidden not in source
    contract = json.loads((PACKAGE / "study-contract.json").read_text(encoding="utf-8"))
    assert contract["recovery"]["new_provider_calls"] == contract["recovery"]["new_process_launches"] == 0
    assert contract["pins"]["source_catalog"]["envelope_sha256_by_cell"] == module().EXPECTED_ENVELOPE_SHA256


def test_cli_emits_utf8_manifest(monkeypatch: pytest.MonkeyPatch, capsysbinary: pytest.CaptureFixture[bytes]):
    value = module()
    monkeypatch.setattr(value, "recover", lambda **_kwargs: {"idea": "n−1"})
    assert value.main(["--source-root", "source", "--target-root", "target"]) == 0
    assert json.loads(capsysbinary.readouterr().out.decode("utf-8")) == {"idea": "n−1"}
