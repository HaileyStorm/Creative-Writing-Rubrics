from __future__ import annotations

import ast
import json
import re
from pathlib import Path

import pytest

from _scoped_module_loader import load_module


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = (
    ROOT
    / "evaluation-results"
    / "hbq-human-alignment-optimizer-v4-balanced-dspy-heldout-exec-v1-public-result-v1"
)
verify = load_module(PACKAGE / "verify.py", name="hanna_v4_heldout_public_result_verify")
materialize = load_module(PACKAGE / "materialize.py", name="hanna_v4_heldout_public_result_materialize")
V3_PACKAGE = ROOT / "evaluation-results" / "hbq-human-alignment-optimizer-v4-balanced-dspy-grok-exec-v3"
v3 = load_module(V3_PACKAGE / "executor.py", name="hanna_v4_feedback_grok_v3_public_result_fixture")


def test_exact_feedback_artifacts_and_public_result_verify_provider_free():
    result = verify.verify(PACKAGE)
    assert result["status"] == "verified"
    assert result["selected_candidate_id"] == "candidate-0ca942ad28cb4104"
    assert result["gain_observed"] is False
    assert result["files"] == verify.FILES


@pytest.mark.parametrize("name", sorted(verify.FILES))
def test_every_published_json_artifact_rejects_byte_tampering(name: str, tmp_path: Path):
    for artifact in verify.FILES:
        (tmp_path / artifact).write_bytes((PACKAGE / artifact).read_bytes())
    raw = bytearray((tmp_path / name).read_bytes())
    raw[len(raw) // 2] ^= 1
    (tmp_path / name).write_bytes(raw)
    with pytest.raises(ValueError, match="hash drifted|invalid JSON|canonical JSON"):
        verify.verify(tmp_path)


def test_feedback_files_are_exact_analyzer_outputs_and_endpoint_separated():
    selection = json.loads((PACKAGE / "grok-selection.json").read_text(encoding="utf-8"))
    result = json.loads((PACKAGE / "endpoint-result.json").read_text(encoding="utf-8"))
    public = json.loads((PACKAGE / "public-result.json").read_text(encoding="utf-8"))
    assert result["grok_selection"] == selection
    assert result["no_pooling"] is True
    assert result["gain_observed"] is False
    assert public["endpoint_metrics"]["grok_primary"]["strict_improvement"] is True
    assert public["endpoint_metrics"]["sol_validation"]["nonreversal"] is False
    assert public["endpoint_metrics"]["grok_primary"]["prompt_group_count"] == 4
    assert public["endpoint_metrics"]["sol_validation"]["prompt_group_count"] == 2


def test_public_artifacts_exclude_private_evidence_surfaces():
    windows_absolute = re.compile(r"^[A-Za-z]:[\\/]")

    def walk(value):
        if isinstance(value, dict):
            assert not verify.DISALLOWED_KEYS.intersection(value)
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)
        elif isinstance(value, str):
            assert not windows_absolute.match(value)

    for name in verify.FILES:
        walk(json.loads((PACKAGE / name).read_text(encoding="utf-8")))


def test_runtime_verifier_and_materializer_have_no_optimizer_or_provider_imports():
    forbidden = {"dspy", "optuna", "requests", "httpx", "openai", "xai_sdk"}
    for name in ("verify.py", "materialize.py"):
        tree = ast.parse((PACKAGE / name).read_text(encoding="utf-8"))
        imports = {
            alias.name.split(".")[0]
            for node in ast.walk(tree)
            if isinstance(node, (ast.Import, ast.ImportFrom))
            for alias in node.names
        }
        assert not forbidden.intersection(imports)


def test_materializer_pins_and_rejects_analyzer_or_verifier_drift(monkeypatch):
    monkeypatch.setattr(materialize, "ANALYZER_SHA256", "0" * 64)
    with pytest.raises(ValueError, match="producer drifted"):
        materialize._load_analyzer()


def test_generated_local_descriptor_is_directly_consumable_by_v3(tmp_path: Path):
    manifest = materialize.feedback_manifest(
        package_root=PACKAGE,
        wave_id="hanna-public-result-wave-v1",
        seed=20260830,
    )
    descriptor = tmp_path / "feedback.json"
    descriptor.write_bytes(materialize.canonical(manifest))
    raw, loaded, authority = v3._feedback(
        descriptor,
        materialize.sha256(descriptor.read_bytes()),
    )
    assert raw == descriptor.read_bytes()
    assert loaded["study_id"] == materialize.PUBLIC_STUDY_ID
    assert loaded["public_result_summary"] == materialize.PUBLIC_RESULT_SUMMARY
    assert loaded["r4_selection_sha256"] == verify.FILES["feedback-selection.json"]
    assert loaded["r4_result_sha256"] == verify.FILES["feedback-result.json"]
    assert set(authority) == {
        "feedback-producer-contract.json",
        "feedback-producer-source.bin",
        "feedback-selection-schema.json",
        "feedback-result-schema.json",
        "feedback-selection.json",
        "feedback-result.json",
    }
