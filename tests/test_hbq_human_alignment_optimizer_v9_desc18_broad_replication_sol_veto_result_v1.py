from __future__ import annotations

import importlib.util
import json
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "evaluation-results" / "hbq-human-alignment-optimizer-v9-desc18-broad-replication-sol-veto-result-v1"
LIVE = Path(r"C:\Users\Haile\Documents\cwr-desc18-broad-sol-veto-926f8f1-20260901a")
COLLECTOR = Path(r"C:\Users\Haile\Documents\cwr-desc18-broad-sol-veto-926f8f1-20260901a.collector.json")
GROK = Path(r"C:\Users\Haile\Documents\cwr-desc18-broad-grok-4d3b2ef-20260901a")
FREEZE = Path(r"C:\Users\Haile\Documents\cwr-hanna-desc18-open-freeze-83d7be7-20260901a")
GROK_COLLECTOR = Path(r"C:\Users\Haile\Documents\cwr-desc18-broad-grok-4d3b2ef-20260901a.reconciled-v1.collector.json")
GROK_RESULT = Path(r"C:\Users\Haile\Documents\cwr-desc18-broad-grok-4d3b2ef-20260901a.optimizer-result-v1.json")


def load():
    spec = importlib.util.spec_from_file_location("_desc18_sol_result", PACKAGE / "verify.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec); sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(spec.name, None)
    return module


def test_package_has_exact_pinned_executor_and_collector():
    value = load(); contract = value.validate_package()
    assert contract["pins"]["executor_commit"] == value.EXECUTOR_COMMIT
    assert contract["pins"]["collector_file_sha256"] == value.COLLECTOR_SHA256


def test_exact_live_replay_recomputes_64_cell_equal_group_result():
    if not all((LIVE.is_dir(), COLLECTOR.is_file(), GROK.is_dir(), FREEZE.is_dir(), GROK_COLLECTOR.is_file(), GROK_RESULT.is_file())):
        pytest.skip("immutable Desc18 evidence unavailable")
    value = load()
    replay = value.replay(execution_root=LIVE, collector_path=COLLECTOR, grok_execution_root=GROK, freeze_root=FREEZE, grok_collector_path=GROK_COLLECTOR, grok_result_path=GROK_RESULT)
    published = value.strict(value.stable(PACKAGE / "result.json"), "published")
    assert replay == published
    metrics = replay["sol_validation"]["metrics"]
    assert [row["equal_group_mae"] for row in metrics] == [1.175173611111111, 1.0699652777777777]
    assert replay["sol_validation"]["survivors"] == [value.CHILD]


def test_wrong_collector_is_rejected_before_projection(tmp_path: Path):
    value = load()
    bad = tmp_path / "collector.json"; bad.write_text("{}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Sol collector"):
        value.replay(execution_root=tmp_path / "out", collector_path=bad, grok_execution_root=tmp_path / "grok", freeze_root=tmp_path / "freeze", grok_collector_path=tmp_path / "grok-collector.json", grok_result_path=tmp_path / "grok-result.json")


def test_coherent_contract_tamper_is_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    value = load(); copy = tmp_path / "package"; shutil.copytree(PACKAGE, copy)
    contract = value.strict((copy / "study-contract.json").read_bytes(), "contract")
    contract["prohibitions"] = []
    (copy / "study-contract.json").write_bytes(value.canonical(contract))
    monkeypatch.setattr(value, "HERE", copy)
    with pytest.raises(ValueError, match="package drifted"):
        value.validate_package()


@pytest.mark.parametrize("kind", ("swap", "incomplete", "aggregate"))
def test_collector_swap_incomplete_or_aggregate_surface_is_rejected(tmp_path: Path, kind: str):
    if not COLLECTOR.is_file():
        pytest.skip("immutable Desc18 collector unavailable")
    value = load(); collector = json.loads(COLLECTOR.read_text(encoding="utf-8")); path = tmp_path / "collector.json"
    if kind == "swap":
        collector["cells"][0], collector["cells"][1] = collector["cells"][1], collector["cells"][0]
    elif kind == "incomplete":
        collector["cells"].pop()
    else:
        collector["aggregate"] = {"equal_group_mae": 0.0}
    path.write_bytes(value.canonical(collector))
    with pytest.raises(ValueError, match="wrong immutable"):
        value.replay(execution_root=LIVE, collector_path=path, grok_execution_root=GROK, freeze_root=FREEZE, grok_collector_path=GROK_COLLECTOR, grok_result_path=GROK_RESULT)
