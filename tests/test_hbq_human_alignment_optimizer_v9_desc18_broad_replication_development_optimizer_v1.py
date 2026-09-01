from __future__ import annotations

import base64
import builtins
import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "evaluation-results" / "hbq-human-alignment-optimizer-v9-desc18-broad-replication-development-optimizer-v1"
CANDIDATES = ROOT / "evaluation-results" / "hbq-human-alignment-optimizer-v9-desc18-broad-replication-candidates-v1" / "study.py"
RECONCILIATION = ROOT / "evaluation-results" / "hbq-human-alignment-optimizer-v9-desc18-broad-replication-grok-reconcile-v1" / "reconcile.py"
LIVE_ROOT = Path(r"C:\Users\Haile\Documents\cwr-desc18-broad-grok-4d3b2ef-20260901a")
LIVE_FREEZE_ROOT = Path(r"C:\Users\Haile\Documents\cwr-hanna-desc18-open-freeze-83d7be7-20260901a")
LIVE_COLLECTOR = Path(r"C:\Users\Haile\Documents\cwr-desc18-broad-grok-4d3b2ef-20260901a.reconciled-v1.collector.json")


def load():
    spec = importlib.util.spec_from_file_location("_desc18_optimizer", PACKAGE / "analyzer.py")
    assert spec and spec.loader
    value = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = value
    try:
        spec.loader.exec_module(value)
    finally:
        sys.modules.pop(spec.name, None)
    return value


def freeze(root: Path):
    spec = importlib.util.spec_from_file_location("_desc18_freeze_test", CANDIDATES)
    assert spec and spec.loader
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value.freeze(root)


def load_reconciliation():
    spec = importlib.util.spec_from_file_location("_desc18_reconciliation_fixture", RECONCILIATION)
    assert spec and spec.loader
    value = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = value
    try:
        spec.loader.exec_module(value)
    finally:
        sys.modules.pop(spec.name, None)
    return value


@pytest.fixture(scope="module")
def evidence(tmp_path_factory: pytest.TempPathFactory):
    if not (LIVE_ROOT.is_dir() and LIVE_FREEZE_ROOT.is_dir() and LIVE_COLLECTOR.is_file()):
        pytest.skip("immutable Desc18 reconciliation evidence is not present")
    collector = tmp_path_factory.mktemp("desc18-reconciliation-evidence") / "collector.json"
    collector.write_bytes(LIVE_COLLECTOR.read_bytes())
    return LIVE_ROOT, LIVE_FREEZE_ROOT, collector


def test_package_pins_committed_reconciliation_contract_readme_and_regression_test(monkeypatch: pytest.MonkeyPatch):
    value = load()
    contract = value.validate_package()
    assert contract["pinned_freeze"]["commit"] == "83d7be718c99c1135302ccb4f8d339a4c68f292f"
    assert contract["pinned_reconciliation"] == {"commit": "b33c501c4d6b87a90d6a5d307f7e025839e4afec", "files": value.RECONCILIATION_FILES, "study_id": value.RECONCILIATION_ID}
    value.validate_reconciliation_binding()
    monkeypatch.setitem(value.RECONCILIATION_FILES, "reconcile.py", "0" * 64)
    with pytest.raises(ValueError, match="binding"):
        value.validate_reconciliation_binding()


def test_import_does_not_load_development_libraries(monkeypatch: pytest.MonkeyPatch):
    original = builtins.__import__

    def blocked(name, *args, **kwargs):
        if name.split(".")[0] in {"dspy", "optuna"}:
            raise AssertionError("development library imported at module load")
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", blocked)
    load()


def test_reconstructs_committed_public_open_fresh96_targets(tmp_path: Path):
    value = load()
    schedule = freeze(tmp_path / "freeze")
    reconstructed = value.reconstruct_open_targets(tmp_path / "freeze")
    assert reconstructed == schedule
    assert len(reconstructed["cells"]) == 64
    assert {row["partition"] for row in reconstructed["cells"]} == {"open_validation_development"}
    assert len({row["prompt_group_id"] for row in reconstructed["cells"]}) == 16


def test_independent_64_receipt_projection_uses_equal_prompt_group_weighting(evidence):
    value = load()
    output_root, freeze_root, collector_path = evidence
    projected = value.replay_projection(output_root=output_root, freeze_root=freeze_root, collector_path=collector_path)
    rows = {row["candidate_id"]: row for row in projected["metrics"]}
    assert rows[value.PARENT]["cells"] == rows[value.CHILD]["cells"] == 32
    assert len(rows[value.PARENT]["group_mae"]) == len(rows[value.CHILD]["group_mae"]) == 16
    assert rows[value.CHILD]["equal_group_mae"] < rows[value.PARENT]["equal_group_mae"]
    optimizer = value.run_optuna(projected["metrics"])
    decision = value.qualify(projected["metrics"], optimizer)
    assert optimizer["sampler"] == "GridSampler" and optimizer["completed_trials"] == 12
    assert decision["qualifiers"] == [value.CHILD]
    dspy = value.build_dspy_evidence(projected["metrics"], decision)
    assert dspy["lm_calls"] == dspy["predict_calls"] == 0 and dspy["evidence_examples"] == 2


@pytest.mark.parametrize("mutation", ("route", "acknowledgement", "request", "receipt_swap"))
def test_reconciliation_replay_rejects_forged_or_misassociated_native_receipts_before_projection(tmp_path: Path, evidence, monkeypatch: pytest.MonkeyPatch, mutation: str):
    value = load()
    output_root, freeze_root, original_collector = evidence
    collector_path = tmp_path / "forged-collector.json"
    evidence = value.strict(original_collector.read_bytes(), "fixture")
    if mutation == "route":
        evidence["route"]["name"] = "forged-route"
    elif mutation == "acknowledgement":
        evidence["authorization_acknowledgement_sha256"] = "0" * 64
    elif mutation == "request":
        first = evidence["cells"][0]
        request = b'{"forged":true}\n'
        first["native_request_base64"] = base64.b64encode(request).decode("ascii")
        first["native_request_sha256"] = value.sha256(request)
    else:
        left, right = evidence["cells"][0], evidence["cells"][1]
        for key in set(left) - {"cell_id"}:
            left[key], right[key] = right[key], left[key]
    collector_path.write_bytes(value.canonical(evidence))
    called = False

    def forbidden(*_args, **_kwargs):
        nonlocal called
        called = True
        raise AssertionError("projection must not run after replay failure")

    monkeypatch.setattr(value, "_project", forbidden)
    with pytest.raises((TypeError, ValueError), match="collector|route|acknowledgement|receipt|execution|binding"):
        value.replay_projection(output_root=output_root, freeze_root=freeze_root, collector_path=collector_path)
    assert called is False


def test_replay_requires_reconciliation_evidence_and_writes_only_fresh_result(tmp_path: Path, evidence):
    value = load()
    output_root, freeze_root, original_collector = evidence
    path = tmp_path / "tampered-collector.json"
    path.write_bytes(original_collector.read_bytes())
    projection = value.replay_projection(output_root=output_root, freeze_root=freeze_root, collector_path=path)
    assert projection["source_execution"]["reconciliation_binding"]["status"] == "exact_committed"
    assert projection["source_execution"]["reconciliation_replay"]["equal_group_projection_ready"] is True
    tampered = value.strict(path.read_bytes(), "fixture")
    tampered["metrics"] = []
    path.write_bytes(value.canonical(tampered))
    with pytest.raises(ValueError, match="collector"):
        value.replay_projection(output_root=output_root, freeze_root=freeze_root, collector_path=path)
    result = tmp_path / "result.json"
    value.write_result(result, {"ok": True})
    with pytest.raises(ValueError, match="fresh plain"):
        value.write_result(result, {"ok": True})
