from __future__ import annotations

import importlib.util
import os
import shutil
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "evaluation-results" / "hbq-human-alignment-optimizer-v5-f20-nextwave-sol6-validation-result-v1"
ENV = {
    "output_root": "CWR_SOL6_RESULT_OUTPUT_ROOT",
    "normalized_root": "CWR_SOL6_NORMALIZED_ROOT",
    "materialization_root": "CWR_SOL6_MATERIALIZATION_ROOT",
    "frozen_successor_path": "CWR_SOL6_FROZEN_SUCCESSOR",
    "hanna_csv_path": "CWR_SOL6_HANNA_CSV",
    "grok_execution_root": "CWR_SOL6_GROK_EXECUTION_ROOT",
    "grok_collector_path": "CWR_SOL6_GROK_COLLECTOR",
    "grok_result_path": "CWR_SOL6_GROK_RESULT",
}
ACK = "2fb371ff82b37fe22d238a223fc030ad7a7bb9a10b672719da081470d25dbe78"


def module():
    spec = importlib.util.spec_from_file_location("_sol6_result", PACKAGE / "verify.py")
    assert spec and spec.loader
    value = importlib.util.module_from_spec(spec); sys.modules[spec.name] = value
    spec.loader.exec_module(value)
    return value


def inputs():
    missing = [value for value in ENV.values() if not os.environ.get(value)]
    if missing:
        pytest.skip("real immutable Sol6 replay inputs require: " + ", ".join(missing))
    return {key: Path(os.environ[value]) for key, value in ENV.items()}


def test_public_package_roundtrip_is_canonical_and_path_free():
    value = module(); result = value.validate_publication()
    assert result["comparison"]["relative_reduction"] > 0
    assert "import dspy" not in (PACKAGE / "verify.py").read_text(encoding="utf-8").lower()
    assert "import optuna" not in (PACKAGE / "verify.py").read_text(encoding="utf-8").lower()


def test_public_validation_rejects_coherent_authority_and_source_rewrite(tmp_path):
    value = module(); copied = tmp_path / "public-package"; shutil.copytree(PACKAGE, copied)
    value.HERE = copied
    result_path, contract_path = copied / "result.json", copied / "study-contract.json"
    result = value.strict(result_path.read_bytes(), "result")
    result["authority"] = dict(result["authority"], selection="selected", promotion="promoted")
    result["claim"] = "PROMOTED_SELECTION"
    result["kind"] = "fake-promoted-result"
    result["source_execution"] = dict(result["source_execution"], v4_commit="0" * 40, grok_result_commit="1" * 40, receipt_chain_sha256="2" * 64)
    internal_result = dict(result); internal_result.pop("result_internal_sha256")
    result["result_internal_sha256"] = value.sha256(internal_result)
    result_path.write_bytes(value.canonical(result))
    contract = value.strict(contract_path.read_bytes(), "contract")
    contract["authority"] = result["authority"]
    contract["kind"] = "fake-promoted-contract"
    contract["result_internal_sha256"] = result["result_internal_sha256"]
    contract["source_execution"] = result["source_execution"]
    contract["publication_manifest"]["bound_files"]["result.json"] = value.sha256(result_path.read_bytes())
    internal_contract = dict(contract); internal_contract.pop("contract_internal_sha256")
    contract["contract_internal_sha256"] = value.sha256(internal_contract)
    contract_path.write_bytes(value.canonical(contract))
    with pytest.raises(ValueError):
        value.validate_publication()


def test_real_immutable_root_replays_six_receipts_without_provider_contact():
    value = module(); replayed = value.replay(**inputs(), acknowledgement_sha256=ACK)
    assert [row["candidate_id"] for row in replayed["metrics"]] == ["normalized-nextwave-08-conservative-hybrid", "candidate-102cc7f06c9a99a7"]
    assert replayed["comparison"]["absolute_delta"] < 0
    assert replayed["evidence_ceiling"] == {"native_endpoint_contact_cardinality": "unproven", "process_lifecycle_receipts": 6, "provider_calls_made": None}
    assert len(replayed["source_execution"]["receipt_chain_sha256"]) == 64


def test_real_root_replay_rejects_reported_field_tampering(tmp_path):
    value = module(); source = inputs(); copied = tmp_path / "copied-root"
    shutil.copytree(source["output_root"], copied)
    record = copied / "sol6-nextwave-score-3e7b525c1969fe87" / "codex-record.json"
    supplied = value.strict(record.read_bytes(), "codex record")
    supplied["reported"]["model"] = "gpt-5.6-sol"
    record.write_bytes(value.canonical(supplied))
    source["output_root"] = copied
    with pytest.raises(ValueError):
        value.replay(**source, acknowledgement_sha256=ACK)


def test_real_root_replay_rejects_event_and_receipt_adversaries(tmp_path):
    value = module(); source = inputs(); copied = tmp_path / "copied-root"
    shutil.copytree(source["output_root"], copied)
    cell = copied / "sol6-nextwave-score-3e7b525c1969fe87"
    (cell / "raw-codex-events.bin").write_bytes(b'{"type":"thread.started","thread_id":"wrong"}\n')
    source["output_root"] = copied
    with pytest.raises(ValueError):
        value.replay(**source, acknowledgement_sha256=ACK)
