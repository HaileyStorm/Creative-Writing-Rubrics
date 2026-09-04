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
SOL = PACKAGE / "development_sol.py"
DEVELOPMENT = PACKAGE / "development.py"
PILOT = PACKAGE / "study.py"
PILOT_TEST = ROOT / "tests" / "test_hbq_human_alignment_optimizer_v14_dspy_train_pilot_sol_v1.py"
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
    module = load(SOL, "v14_development_sol")
    development = load(DEVELOPMENT, "v14_development_sol_fixture")
    return module, development


def common(tmp_path: Path) -> dict[str, Any]:
    pilot = load(PILOT, "v14_development_sol_pilot")
    support = load(V12_TEST, "v14_development_sol_v12_support")
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


def resolution_args(args: dict[str, Any]) -> dict[str, Any]:
    return {name: args[name] for name in ("split_manifest", "hanna_csv", "successor_contract", "recovered_descendant")}


def report_args(args: dict[str, Any]) -> dict[str, Any]:
    return {name: args[name] for name in ("output_root", "authorization_acknowledgement_sha256", "split_manifest", "hanna_csv", "successor_contract", "recovered_descendant")}


def test_exact_26_development_payloads_match_grok_schedule(value: tuple[Any, Any], tmp_path: Path):
    module, development = value
    args = common(tmp_path)
    resolution = module._resolution(**resolution_args(args))
    schedule = development.schedule(**resolution_args(args))
    source = {(row["candidate_id"], row["item_id"]): row for row in schedule["cells"]}
    assert len(resolution["rows"]) == len(source) == 26
    assert {row["candidate_id"] for row in resolution["rows"]} == {module.CHILD20, module.DESCENDANT}
    assert len({row["item_id"] for row in resolution["rows"]}) == 13
    assert len({row["prompt_group_id"] for row in resolution["rows"]}) == 7
    for row in resolution["rows"]:
        original = source[(row["candidate_id"], row["item_id"])]
        payload = base64.b64decode(row["payload_base64"], validate=True)
        assert row["payload_base64"] == original["payload_base64"]
        assert row["payload_sha256"] == module._base().sha256(payload)
        assert original["endpoint_payload_sha256s"] == {"grok_primary": row["payload_sha256"], "sol_later": row["payload_sha256"]}
        assert "target" not in json.loads(payload)
    assert "import dspy" not in SOL.read_text(encoding="utf-8").lower()


def test_prepare_is_provider_free_and_rejects_immutable_source_parent_overlap(value: tuple[Any, Any], tmp_path: Path):
    module, _development = value
    args = common(tmp_path)
    call_args = {name: item for name, item in args.items() if name != "route_evidence"}
    result = module.prepare_all(**call_args)
    assert result == {"study_id": module.STUDY_ID, "state": "prepared_exact_26_matched_sol_development_cells", "cells": 26, "groups": 7, "provider_calls_made": 0, "process_launches": 0, "max_concurrency": 10}
    assert len(list(args["output_root"].iterdir())) == 26
    for index, protected in enumerate((SPLIT, CSV, CONTRACT, args["recovered_descendant"])):
        overlap = Path(protected).parent / f"v14-development-sol-overlap-{tmp_path.name}-{index}"
        assert not overlap.exists()
        with pytest.raises(ValueError):
            module.prepare_all(**{**call_args, "output_root": overlap})
        assert not overlap.exists()


def test_native_fixture_has_26_unique_receipts_and_equal_group_metrics(value: tuple[Any, Any], tmp_path: Path):
    module, _development = value
    args = common(tmp_path)
    call_args = {name: item for name, item in args.items() if name != "route_evidence"}
    module.prepare_all(**call_args)
    rows = module._resolution(**resolution_args(args))["rows"]
    support = load(PILOT_TEST, "v14_development_sol_native_support")
    contacts: list[str] = []
    concurrency = {"active": 0, "maximum": 0}
    fixture_value = SimpleNamespace(DIMS=module.DIMS, sha256=module._base().sha256)
    results = module.execute_wave(**call_args, allow_remote=True, call_codex=support.fake_codex(fixture_value, rows, contacts, concurrency))
    assert len(results) == len(contacts) == 26 and 1 <= concurrency["maximum"] <= 10
    report = module.report(**report_args(args))
    assert (report["endpoint"], report["partition"]) == ("sol_later", "development")
    assert len(report["cells"]) == report["unique_thread_ids"] == report["unique_session_ids"] == 26
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
    assert all(row["item_count"] == 13 and row["group_count"] == len(row["per_group_mean_item_mae"]) == 7 for row in report["metrics"])
    assert set(report["rank_correlations"]) == {module.CHILD20, module.DESCENDANT}
    assert all(set(report["rank_correlations"][candidate]) == {"item_13", "group_mean_7"} for candidate in report["rank_correlations"])
    before = {path.relative_to(args["output_root"]).as_posix(): path.read_bytes() for path in args["output_root"].rglob("*") if path.is_file()}
    with pytest.raises(ValueError, match="resend|terminal|inventory"):
        module.execute_wave(**call_args, allow_remote=True, call_codex=lambda **_kwargs: pytest.fail("replay contacted Sol"))
    assert {path.relative_to(args["output_root"]).as_posix(): path.read_bytes() for path in args["output_root"].rglob("*") if path.is_file()} == before
