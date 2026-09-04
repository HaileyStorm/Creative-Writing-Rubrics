from __future__ import annotations

import base64
import importlib.util
import json
import math
from collections import defaultdict
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "evaluation-results" / "hbq-human-alignment-optimizer-v14-dspy-train-pilot-v1"
SOL = PACKAGE / "expansion_sol.py"
EXPANSION = PACKAGE / "expansion.py"
PILOT_TEST = ROOT / "tests" / "test_hbq_human_alignment_optimizer_v14_dspy_train_pilot_sol_v1.py"
PILOT_STUDY = PACKAGE / "study.py"
V12_TEST = ROOT / "tests" / "test_hbq_human_alignment_optimizer_v12_development_sol_exec_v1.py"
SPLIT = Path(r"C:\Users\Haile\Documents\cwr-hanna-optimizer-grok-primary-dev-20260829-d189d71\split-manifest.json")
CSV = Path(r"C:\Users\Haile\Documents\cwr-hanna-pinned-data-282f275\hanna_stories_annotations.csv")
CONTRACT = Path(r"C:\Users\Haile\Documents\cwr-hanna-successor-fresh88-freeze-v4\frozen-successor-contract.json")
ACK = "a" * 64


def load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def value():
    module = load(SOL, "v14_expansion_sol")
    expansion = load(EXPANSION, "v14_expansion_fixture")
    return module, expansion


def common(tmp_path: Path, expansion: Any) -> dict[str, Any]:
    pilot = load(PILOT_STUDY, "v14_expansion_sol_pilot_fixture")
    support = load(V12_TEST, "v14_expansion_sol_v12_support")
    route, evidence = support.sol_route()
    queue_root = tmp_path / "queue"
    queue_root.mkdir()
    return {
        "output_root": tmp_path / "output",
        "queue_root": queue_root,
        "authorization_acknowledgement_sha256": ACK,
        "split_manifest": SPLIT,
        "hanna_csv": CSV,
        "successor_contract": CONTRACT,
        "recovered_descendant": pilot.RECOVERED,
        "broker_factory": lambda _root: support.Broker(route),
        "route_evidence": evidence,
    }


def resolution_args(common: dict[str, Any]) -> dict[str, Any]:
    return {name: common[name] for name in ("split_manifest", "hanna_csv", "successor_contract", "recovered_descendant")}


def report_args(common: dict[str, Any]) -> dict[str, Any]:
    return {name: common[name] for name in ("output_root", "authorization_acknowledgement_sha256", "split_manifest", "hanna_csv", "successor_contract", "recovered_descendant")}


def test_frozen_expansion_schedule_has_exact_88_grok_sol_payload_pairs(value: tuple[Any, Any], tmp_path: Path):
    module, expansion = value
    args = common(tmp_path, expansion)
    resolution = module._resolution(**resolution_args(args))
    schedule = expansion.schedule(**resolution_args(args))
    source = {(row["candidate_id"], row["item_id"]): row for row in schedule["cells"]}
    assert len(resolution["rows"]) == len(source) == 88
    assert {row["candidate_id"] for row in resolution["rows"]} == {module.CHILD20, module.DESCENDANT}
    assert {row["prompt_group_id"] for row in resolution["rows"]} == {row["prompt_group_id"] for row in schedule["cells"]}
    for row in resolution["rows"]:
        source_row = source[(row["candidate_id"], row["item_id"])]
        payload = base64.b64decode(row["payload_base64"], validate=True)
        assert row["payload_base64"] == source_row["payload_base64"]
        assert row["payload_sha256"] == module._base().sha256(payload)
        assert source_row["endpoint_payload_sha256s"]["grok_primary"] == source_row["endpoint_payload_sha256s"]["sol_later"] == row["payload_sha256"]
        assert "target" not in json.loads(payload)
    text = SOL.read_text(encoding="utf-8").lower()
    assert "import dspy" not in text and "grok_root" not in text


def test_prepare_is_provider_free_and_rejects_each_source_parent_overlap(value: tuple[Any, Any], tmp_path: Path):
    module, expansion = value
    args = common(tmp_path, expansion)
    call_args = {name: item for name, item in args.items() if name != "route_evidence"}
    result = module.prepare_all(**call_args)
    assert result == {"study_id": module.STUDY_ID, "state": "prepared_exact_88_matched_sol_train_cells", "cells": 88, "groups": 22, "provider_calls_made": 0, "process_launches": 0, "max_concurrency": 10}
    assert len(list(args["output_root"].iterdir())) == 88
    for index, protected in enumerate((SPLIT, CSV, CONTRACT, args["recovered_descendant"])):
        overlap = Path(protected).parent / f"v14-expansion-sol-overlap-{tmp_path.name}-{index}"
        assert not overlap.exists()
        with pytest.raises(ValueError):
            module.prepare_all(**{**call_args, "output_root": overlap})
        assert not overlap.exists()


def test_sol_expansion_uses_bounded_native_fixture_and_independent_group_mae(value: tuple[Any, Any], tmp_path: Path):
    module, expansion = value
    args = common(tmp_path, expansion)
    call_args = {name: item for name, item in args.items() if name != "route_evidence"}
    module.prepare_all(**call_args)
    rows = module._resolution(**resolution_args(args))["rows"]
    support = load(PILOT_TEST, "v14_expansion_sol_native_support")
    contacts: list[str] = []
    concurrency = {"active": 0, "maximum": 0}
    fixture_value = SimpleNamespace(DIMS=module.DIMS, sha256=module._base().sha256)
    results = module.execute_wave(**call_args, allow_remote=True, call_codex=support.fake_codex(fixture_value, rows, contacts, concurrency))
    assert len(results) == len(contacts) == 88 and 1 <= concurrency["maximum"] <= 10
    report = module.report(**report_args(args))
    assert (report["endpoint"], report["partition"]) == ("sol_later", "train")
    assert len(report["cells"]) == report["unique_thread_ids"] == report["unique_session_ids"] == 88
    assert all(all(math.isfinite(cell["scores"][name]) and cell["coverage"][name] is False for name in module.DIMS) for cell in report["cells"])
    assert any(all(cell["scores"][name] == 0.0 for name in module.DIMS) for cell in report["cells"])
    expected = {}
    for candidate in (module.CHILD20, module.DESCENDANT):
        groups: dict[str, list[float]] = defaultdict(list)
        for cell in report["cells"]:
            if cell["candidate_id"] == candidate:
                groups[cell["prompt_group_id"]].append(cell["per_item_mae"])
        expected[candidate] = sum(sum(errors) / len(errors) for errors in groups.values()) / len(groups)
    assert {row["candidate_id"]: row["equal_group_mean_item_mae"] for row in report["metrics"]} == pytest.approx(expected)
    assert all(row["item_count"] == 44 and row["group_count"] == len(row["per_group_mean_item_mae"]) == 22 for row in report["metrics"])
    before = {path.relative_to(args["output_root"]).as_posix(): path.read_bytes() for path in args["output_root"].rglob("*") if path.is_file()}
    with pytest.raises(ValueError, match="resend|terminal|inventory"):
        module.execute_wave(**call_args, allow_remote=True, call_codex=lambda **_kwargs: pytest.fail("replay contacted Sol"))
    assert {path.relative_to(args["output_root"]).as_posix(): path.read_bytes() for path in args["output_root"].rglob("*") if path.is_file()} == before
