from __future__ import annotations

import hashlib
import importlib.util
import json
import shutil
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "evaluation-results" / "hbq-human-alignment-optimizer-v5-f20-broader-development-grok-result-v2-v3-exec"
FROZEN = Path(r"C:\Users\Haile\Documents\cwr-hanna-broader-freeze-436da1e-20260831a")
NORMALIZED = Path(r"C:\Users\Haile\Documents\cwr-hanna-nextwave-normalized-d5e95ba-20260831a")
MATERIALIZATION = Path(r"C:\Users\Haile\Documents\cwr-hanna-v5-mixed-materialization-9bb20be-20260830a")
SUCCESSOR = Path(r"C:\Users\Haile\Documents\cwr-hanna-successor-fresh88-freeze-v4\frozen-successor-contract.json")
CSV = Path(r"C:\Users\Haile\Documents\cwr-hanna-pinned-data-282f275\hanna_stories_annotations.csv")
OUTPUT = Path(r"C:\Users\Haile\Documents\cwr-hanna-broader-grok-exec-ab8613e-20260831a")
COLLECTOR = Path(r"C:\Users\Haile\Documents\cwr-hanna-broader-grok-exec-ab8613e-20260831a-collector.json")


def module():
    spec = importlib.util.spec_from_file_location("_broader_grok_result_v2_test", PACKAGE / "verify.py")
    assert spec and spec.loader
    value = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = value
    spec.loader.exec_module(value)
    return value


def inputs():
    required = (FROZEN, NORMALIZED, MATERIALIZATION, SUCCESSOR, CSV, OUTPUT, COLLECTOR)
    if not all(path.exists() for path in required):
        pytest.skip("real immutable V3 replay inputs are unavailable")
    return {"frozen_root": FROZEN, "normalized_root": NORMALIZED, "materialization_root": MATERIALIZATION, "frozen_successor_path": SUCCESSOR, "hanna_csv_path": CSV, "output_root": OUTPUT, "collector_path": COLLECTOR}


def rehash_public(value, root: Path, result: dict):
    result.pop("result_internal_sha256", None)
    result["result_internal_sha256"] = value.sha256(result)
    (root / "result.json").write_bytes(value.canonical(result))
    contract = value.strict((root / "study-contract.json").read_bytes(), "contract")
    for name in ("authority", "evidence_ceiling", "source_execution"):
        contract[name] = result[name]
    contract["result_internal_sha256"] = result["result_internal_sha256"]
    contract["publication_manifest"]["bound_files"] = {name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in ("README.md", "result.json", "verify.py")}
    contract.pop("contract_internal_sha256", None)
    contract["contract_internal_sha256"] = value.sha256(contract)
    (root / "study-contract.json").write_bytes(value.canonical(contract))


def test_public_package_is_canonical_path_free_and_grok_only():
    value = module(); result = value.validate_publication()
    assert value.main([]) == 0
    assert result["selection"]["candidate_id"] == "broader-nextwave-13-missing_evidence_not_no"
    assert result["selection"]["equal_group_mae"] == pytest.approx(0.7380952380952381)
    assert result["authority"]["selection"] == "grok_development_only"
    source = (PACKAGE / "verify.py").read_text(encoding="utf-8").lower()
    assert "import dspy" not in source and "import optuna" not in source


def test_complete_immutable_v3_root_replays_without_provider_contact():
    value = module(); replayed = value.replay(**inputs())
    assert replayed == value.validate_publication()
    assert replayed["source_execution"]["collector_sha256"] == value.COLLECTOR_SHA256
    assert replayed["evidence_ceiling"] == {"native_endpoint_contact_cardinality": "unproven", "process_lifecycle_receipts": 35, "provider_calls_made": None}


def test_public_tampering_and_wrong_collector_are_rejected(tmp_path):
    value = module(); copied = tmp_path / "public"
    shutil.copytree(PACKAGE, copied)
    result_path = copied / "result.json"
    result = value.strict(result_path.read_bytes(), "result")
    result["selection"]["candidate_id"] = "tampered"
    result_path.write_bytes(value.canonical(result))
    original = value.HERE; value.HERE = copied
    try:
        with pytest.raises(ValueError):
            value.validate_publication()
    finally:
        value.HERE = original
    wrong = tmp_path / "collector.json"; wrong.write_bytes(b"{}\n")
    source = inputs(); source["collector_path"] = wrong
    with pytest.raises(ValueError, match="collector"):
        value.replay(**source)


def test_coherently_rehashed_authority_source_and_metric_promotions_are_rejected(tmp_path):
    value = module()
    mutations = (
        lambda result: (result["authority"].update({"promotion": "published", "generalization": "claimed"}), result.update({"claim": "GENERALIZED_AND_PROMOTED"})),
        lambda result: result["source_execution"].update({"collector_sha256": "0" * 64}),
        lambda result: (result["metrics"][0].update({"equal_group_mae": 0.7, "group_mae": {key: 0.7 for key in result["metrics"][0]["group_mae"]}}), result.update(dict(zip(("selection", "parent_vs_descendant"), value._derived(result))))),
    )
    for index, mutate in enumerate(mutations):
        copied = tmp_path / f"coherent-{index}"; shutil.copytree(PACKAGE, copied)
        result = json.loads((copied / "result.json").read_text(encoding="utf-8"))
        mutate(result); rehash_public(value, copied, result)
        original = value.HERE; value.HERE = copied
        try:
            with pytest.raises(ValueError, match="immutable public semantic"):
                value.validate_publication()
        finally:
            value.HERE = original
