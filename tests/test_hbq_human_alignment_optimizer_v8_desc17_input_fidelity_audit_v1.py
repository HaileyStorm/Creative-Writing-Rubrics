from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "evaluation-results" / "hbq-human-alignment-optimizer-v8-desc17-input-fidelity-audit-v1"


def module():
    spec = importlib.util.spec_from_file_location("_desc17_input_fidelity_audit", PACKAGE / "audit.py")
    assert spec and spec.loader
    value = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = value
    try:
        spec.loader.exec_module(value)
    finally:
        sys.modules.pop(spec.name, None)
    return value


def collector_path() -> Path:
    documents = os.environ.get("CWR_DESC17_INPUT_AUDIT_EVIDENCE_DOCUMENTS")
    if documents is None:
        pytest.skip("set CWR_DESC17_INPUT_AUDIT_EVIDENCE_DOCUMENTS to replay the immutable desc17 collector")
    return Path(documents) / "cwr-desc17-generalization-grok-69e7a40-20260901d.collector.json"


def test_package_records_a_withdrawal_without_mutating_the_original_result():
    value = module()
    public = value.validate_package()
    assert public["authority"]["desc17_semantic_conclusion"] == "withdrawn"
    assert public["scope"] == {"affected": ["desc17"], "outside_audit_scope": ["desc15", "desc16", "Fresh88"]}
    assert public["original_result"]["file_sha256"] == value.ORIGINAL_SHA256
    assert public["original_result"]["publication_manifest_file_sha256"] == value.ORIGINAL_MANIFEST_SHA256


def test_original_result_and_manifest_are_bound_to_the_published_commit():
    value = module()
    value._original_result()


def test_immutable_collector_replay_counts_every_input_and_response_defect():
    value = module()
    result = value.audit(collector_path())
    assert result["defect_counts"] == value.EXPECTED
    assert result["defect_counts"]["opaque_prompt_writing_payload_cells"] == 52
    assert result["defect_counts"]["all_zero_score_cells"] == 10
    assert result["defect_counts"]["evidence_x_cells"] == 2
    assert result["defect_counts"]["placeholder_or_searching_response_cells"] == 4
    assert result["defect_counts"]["response_fidelity_signal_union_cells"] == 12


def test_collector_hash_tamper_is_rejected_before_any_withdrawal_result(tmp_path: Path):
    value = module()
    tampered = tmp_path / "collector.json"
    tampered.write_bytes(b"{}\n")
    with pytest.raises(ValueError, match="bytes drifted"):
        value.audit(tampered)


def test_duplicate_json_keys_are_rejected():
    value = module()
    with pytest.raises(ValueError, match="invalid collector"):
        value.mapping(b'{"cells":[],"cells":[]}\n', "collector", canonical_required=True)
