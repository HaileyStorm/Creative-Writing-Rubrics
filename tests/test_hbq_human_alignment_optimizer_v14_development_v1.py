from __future__ import annotations

import base64
import hashlib
import importlib.util
import json
import math
from collections import defaultdict
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "evaluation-results" / "hbq-human-alignment-optimizer-v14-dspy-train-pilot-v1"
SOURCE = PACKAGE / "development.py"
PILOT_TEST = ROOT / "tests" / "test_hbq_human_alignment_optimizer_v14_dspy_train_pilot_v1.py"
SPLIT = Path(r"C:\Users\Haile\Documents\cwr-hanna-optimizer-grok-primary-dev-20260829-d189d71\split-manifest.json")
CSV = Path(r"C:\Users\Haile\Documents\cwr-hanna-pinned-data-282f275\hanna_stories_annotations.csv")
CONTRACT = Path(r"C:\Users\Haile\Documents\cwr-hanna-successor-fresh88-freeze-v4\frozen-successor-contract.json")
RECOVERED = Path(r"C:\Users\Haile\Documents\cwr-hanna-dspy-proposal-recovery-cbe403dd-20260904-r1\recovered-descendant.json")
CHILD20 = "broader-nextwave-20-missing_evidence_not_no-referent-evidence"
DESCENDANT = "candidate-62195a3b90edd96d"
ACK = "a" * 64


def module():
    spec = importlib.util.spec_from_file_location("v14_dspy_development", SOURCE)
    assert spec and spec.loader
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def pilot_support():
    spec = importlib.util.spec_from_file_location("v14_dspy_train_pilot_support", PILOT_TEST)
    assert spec and spec.loader
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def common(tmp_path: Path) -> dict:
    return {
        "output_root": tmp_path / "output",
        "queue_root": tmp_path / "queue",
        "authorization_acknowledgement_sha256": ACK,
        "split_manifest": SPLIT,
        "hanna_csv": CSV,
        "successor_contract": CONTRACT,
        "recovered_descendant": RECOVERED,
        "route_provider": pilot_support().route_provider(),
    }


def report_args(args: dict) -> dict:
    return {key: args[key] for key in args if key not in {"queue_root", "route_provider"}}


def test_schedule_is_fresh_development_only_26_cell_panel_with_frozen_payloads(tmp_path: Path):
    value = module()
    schedule = value.schedule(split_manifest=SPLIT, hanna_csv=CSV, successor_contract=CONTRACT, recovered_descendant=RECOVERED)
    cells = schedule["cells"]
    assert len(cells) == 26
    assert {cell["candidate_id"] for cell in cells} == {CHILD20, DESCENDANT}
    assert {cell["partition"] for cell in cells} == {"development"}
    assert len({cell["item_id"] for cell in cells}) == 13
    assert schedule["authority"]["confirmation"] == "none"
    assert schedule["authority"]["previous_v12"] == "unchanged_not_adopted"
    groups: dict[str, set[str]] = defaultdict(set)
    paired: dict[str, set[str]] = defaultdict(set)
    for cell in cells:
        groups[cell["prompt_group_id"]].add(cell["item_id"])
        paired[cell["item_id"]].add(cell["candidate_id"])
        payload = base64.b64decode(cell["payload_base64"], validate=True)
        assert value.sha256(payload) == cell["payload_sha256"]
        assert "target" not in json.loads(payload)
        assert cell["endpoint_payload_sha256s"]["grok_primary"] == cell["endpoint_payload_sha256s"]["sol_later"] == cell["payload_sha256"]
    assert sorted(map(len, groups.values())) == [1, 2, 2, 2, 2, 2, 2]
    assert all(candidates == {CHILD20, DESCENDANT} for candidates in paired.values())
    copied = tmp_path / "recovered-descendant.json"
    copied.write_bytes(RECOVERED.read_bytes() + b"x")
    with pytest.raises(ValueError, match="recovered descendant source drifted"):
        value.schedule(split_manifest=SPLIT, hanna_csv=CSV, successor_contract=CONTRACT, recovered_descendant=copied)


def test_prepare_is_provider_free_and_rejects_output_inside_each_immutable_input_parent(tmp_path: Path):
    value = module()
    prepared = value.prepare_all(**common(tmp_path))
    assert prepared["logical_cells"] == len(prepared["prepared_cells"]) == 26
    assert prepared["provider_calls_made"] == prepared["process_launches"] == 0

    for ordinal, source_path in enumerate((RECOVERED, SPLIT, CSV, CONTRACT)):
        output_root = source_path.parent / f"v14-development-overlap-{ordinal}"
        assert not output_root.exists()
        before = {path.name for path in source_path.parent.iterdir()}
        args = common(tmp_path)
        args["output_root"] = output_root
        with pytest.raises(ValueError):
            value.prepare_all(**args)
        assert not output_root.exists()
        assert {path.name for path in source_path.parent.iterdir()} == before


def test_bounded_one_shot_native_26_report_retains_zero_false_coverage_and_empty_thought(tmp_path: Path):
    value, args = module(), common(tmp_path)
    schedule = value.schedule(split_manifest=SPLIT, hanna_csv=CSV, successor_contract=CONTRACT, recovered_descendant=RECOVERED)
    value.prepare_all(**args)
    contacts: list[str] = []
    concurrency = {"active": 0, "maximum": 0}
    runner = pilot_support().native_runner(value, schedule["cells"], contacts, concurrency)
    results = value.execute_wave(**args, allow_remote=True, runner=runner)
    assert len(results) == len(contacts) == 26
    assert set(contacts) == {cell["cell_id"] for cell in schedule["cells"]}
    assert 2 <= concurrency["maximum"] <= 10
    assert all(result["process_launches"] == 1 and result["native_endpoint_contact_cardinality"] == "unproven" for result in results)

    report = value.report(**report_args(args))
    assert len(report["cells"]) == report["unique_request_ids"] == report["unique_session_ids"] == 26
    assert any(all(cell["scores"][dimension] == 0.0 for dimension in value.DIMS) for cell in report["cells"])
    assert all(math.isfinite(cell["scores"][dimension]) and cell["coverage"][dimension] is False for cell in report["cells"] for dimension in value.DIMS)
    expected: dict[str, float] = {}
    for candidate in (CHILD20, DESCENDANT):
        groups: dict[str, list[float]] = defaultdict(list)
        for cell in report["cells"]:
            if cell["candidate_id"] == candidate:
                groups[cell["prompt_group_id"]].append(sum(abs(cell["scores"][dimension] - cell["target"][dimension]) for dimension in value.DIMS) / len(value.DIMS))
        expected[candidate] = sum(sum(errors) / len(errors) for errors in groups.values()) / len(groups)
    assert {row["candidate_id"]: row["equal_group_mean_item_mae"] for row in report["metrics"]} == pytest.approx(expected)
    assert all(row["item_count"] == 13 and row["group_count"] == 7 and len(row["per_group_mean_item_mae"]) == 7 for row in report["metrics"])

    before = {path.relative_to(args["output_root"]).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest() for path in args["output_root"].rglob("*") if path.is_file()}
    with pytest.raises(ValueError, match="no resend|terminal evidence|root inventory"):
        value.execute_wave(**args, allow_remote=True, runner=lambda **_kwargs: pytest.fail("resend invoked runner"))
    after = {path.relative_to(args["output_root"]).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest() for path in args["output_root"].rglob("*") if path.is_file()}
    assert after == before
