from __future__ import annotations

import importlib.util
import os
import shutil
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "evaluation-results" / "hbq-human-alignment-optimizer-v5-f20-broader-development-sol-result-v1"
ENV = {
    "output_root": "CWR_BROADER_SOL_RESULT_OUTPUT_ROOT",
    "frozen_root": "CWR_BROADER_SOL_FROZEN_ROOT",
    "normalized_root": "CWR_BROADER_SOL_NORMALIZED_ROOT",
    "materialization_root": "CWR_BROADER_SOL_MATERIALIZATION_ROOT",
    "frozen_successor_path": "CWR_BROADER_SOL_FROZEN_SUCCESSOR",
    "hanna_csv_path": "CWR_BROADER_SOL_HANNA_CSV",
    "grok_execution_root": "CWR_BROADER_SOL_GROK_EXECUTION_ROOT",
    "grok_collector_path": "CWR_BROADER_SOL_GROK_COLLECTOR",
    "grok_result_path": "CWR_BROADER_SOL_GROK_RESULT",
}
ACK = "2fb371ff82b37fe22d238a223fc030ad7a7bb9a10b672719da081470d25dbe78"


def module():
    spec = importlib.util.spec_from_file_location("_broader_sol_result", PACKAGE / "verify.py")
    assert spec and spec.loader
    value = importlib.util.module_from_spec(spec); sys.modules[spec.name] = value
    spec.loader.exec_module(value)
    return value


def inputs():
    missing = [value for value in ENV.values() if not os.environ.get(value)]
    if missing:
        pytest.skip("real immutable broader Sol replay inputs require: " + ", ".join(missing))
    return {key: Path(os.environ[value]) for key, value in ENV.items()}


def test_public_package_is_canonical_and_exactly_descriptive():
    value = module(); result = value.validate_publication()
    assert result["comparison"]["baseline_to_descendant"]["relative_reduction"] > 0
    source = (PACKAGE / "verify.py").read_text(encoding="utf-8").lower()
    assert "import dspy" not in source and "import optuna" not in source


def test_public_validation_rejects_coherent_authority_and_source_rewrite(tmp_path):
    value = module(); copied = tmp_path / "public-package"; shutil.copytree(PACKAGE, copied); value.HERE = copied
    result_path, contract_path = copied / "result.json", copied / "study-contract.json"
    result = value.strict(result_path.read_bytes(), "result")
    result["authority"] = dict(result["authority"], selection="selected", promotion="promoted")
    result["claim"] = "PROMOTED_SELECTION"; result["kind"] = "fake-result"
    result["source_execution"] = dict(result["source_execution"], source_commit="0" * 40, grok_result_commit="1" * 40, receipt_chain_sha256="2" * 64)
    internal_result = dict(result); internal_result.pop("result_internal_sha256"); result["result_internal_sha256"] = value.sha256(internal_result)
    result_path.write_bytes(value.canonical(result))
    contract = value.strict(contract_path.read_bytes(), "contract")
    contract["authority"] = result["authority"]; contract["kind"] = "fake-contract"; contract["result_internal_sha256"] = result["result_internal_sha256"]; contract["source_execution"] = result["source_execution"]
    contract["publication_manifest"]["bound_files"]["result.json"] = value.sha256(result_path.read_bytes())
    internal_contract = dict(contract); internal_contract.pop("contract_internal_sha256"); contract["contract_internal_sha256"] = value.sha256(internal_contract)
    contract_path.write_bytes(value.canonical(contract))
    with pytest.raises(ValueError):
        value.validate_publication()


def test_public_validation_rejects_recalculated_metric_rewrite(tmp_path):
    value = module(); copied = tmp_path / "public-package"; shutil.copytree(PACKAGE, copied); value.HERE = copied
    result_path, contract_path = copied / "result.json", copied / "study-contract.json"
    result = value.strict(result_path.read_bytes(), "result")
    groups = {row["candidate_id"]: dict(row["group_mae"]) for row in result["metrics"]}
    groups[value.BASELINE] = {group: 0.5 for group in groups[value.BASELINE]}
    result["metrics"], result["comparison"] = value._metrics(groups)
    internal_result = dict(result); internal_result.pop("result_internal_sha256"); result["result_internal_sha256"] = value.sha256(internal_result)
    result_path.write_bytes(value.canonical(result))
    contract = value.strict(contract_path.read_bytes(), "contract")
    contract["result_internal_sha256"] = result["result_internal_sha256"]
    contract["publication_manifest"]["bound_files"]["result.json"] = value.sha256(result_path.read_bytes())
    internal_contract = dict(contract); internal_contract.pop("contract_internal_sha256"); contract["contract_internal_sha256"] = value.sha256(internal_contract)
    contract_path.write_bytes(value.canonical(contract))
    with pytest.raises(ValueError):
        value.validate_publication()


def test_real_immutable_root_replays_twenty_one_receipts_without_provider_contact():
    value = module(); replayed = value.replay(**inputs(), acknowledgement_sha256=ACK)
    assert [row["candidate_id"] for row in replayed["metrics"]] == [value.DESCENDANT, value.PARENT, value.BASELINE]
    assert replayed["comparison"]["baseline_to_parent"]["absolute_delta"] < 0
    assert replayed["comparison"]["parent_to_descendant"]["absolute_delta"] < 0
    assert replayed["evidence_ceiling"] == value.EVIDENCE_CEILING


def test_real_root_replay_rejects_reported_record_and_event_tampering(tmp_path):
    value = module(); source = inputs(); copied = tmp_path / "copied-root"; shutil.copytree(source["output_root"], copied)
    cell = copied / "broader-sol-0075a2f280bebea8"; record = cell / "codex-record.json"
    document = value.strict(record.read_bytes(), "record"); document["reported"]["model"] = "gpt-5.6-sol"; record.write_bytes(value.canonical(document))
    source["output_root"] = copied
    with pytest.raises(ValueError):
        value.replay(**source, acknowledgement_sha256=ACK)
    shutil.rmtree(copied); shutil.copytree(inputs()["output_root"], copied)
    (copied / "broader-sol-0075a2f280bebea8" / "raw-codex-events.bin").write_bytes(b'{"type":"thread.started","thread_id":"wrong"}\n')
    with pytest.raises(ValueError):
        value.replay(**source, acknowledgement_sha256=ACK)
