from __future__ import annotations

import base64
import importlib.util
import json
import math
import threading
import time
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "evaluation-results" / "hbq-human-alignment-optimizer-v14-dspy-train-pilot-v1"
SOL = PACKAGE / "sol.py"
STUDY = PACKAGE / "study.py"
V12_TEST = ROOT / "tests" / "test_hbq_human_alignment_optimizer_v12_development_sol_exec_v1.py"
NATIVE = ROOT / "evaluation-results" / "hbq-human-alignment-optimizer-v4-native-subscription-exec-v3" / "executor.py"
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
    module = load(SOL, "v14_sol")
    study = load(STUDY, "v14_sol_study_fixture")
    return module, study


def common(tmp_path: Path, study: Any) -> dict[str, Any]:
    support = load(V12_TEST, "v14_sol_v12_support")
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
        "recovered_descendant": study.RECOVERED,
        "broker_factory": lambda _root: support.Broker(route),
        "route_evidence": evidence,
    }


def resolution_args(common: dict[str, Any]) -> dict[str, Any]:
    return {name: common[name] for name in ("split_manifest", "hanna_csv", "successor_contract", "recovered_descendant")}


def report_args(common: dict[str, Any]) -> dict[str, Any]:
    return {name: common[name] for name in ("output_root", "authorization_acknowledgement_sha256", "split_manifest", "hanna_csv", "successor_contract", "recovered_descendant")}


def fake_codex(value: Any, rows: tuple[dict[str, Any], ...], contacts: list[str], concurrency: dict[str, int]):
    targets = {row["cell_id"]: row["target"] for row in rows}
    zero_cell = min(row["cell_id"] for row in rows)
    lock = threading.Lock()

    def invoke(**kwargs: Any):
        root = Path(kwargs["output_dir"])
        cell_id = root.name
        with lock:
            concurrency["active"] += 1
            concurrency["maximum"] = max(concurrency["maximum"], concurrency["active"])
        try:
            time.sleep(0.01)
            target = targets[cell_id]
            scores = {name: float(target[name]) + 0.25 for name in value.DIMS}
            if cell_id == zero_cell:
                scores = {name: 0.0 for name in value.DIMS}
            answer = {"scores": scores, "evidence": {name: "Fixture evidence is present." for name in value.DIMS}, "coverage": {name: False for name in value.DIMS}}
            final = json.dumps(answer, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            responses = root / "responses"
            responses.mkdir(exist_ok=True)
            kwargs["before_provider_attempt"]()
            events = b"".join(
                json.dumps(event, ensure_ascii=False, separators=(",", ":")).encode("utf-8") + b"\n"
                for event in (
                    {"type": "thread.started", "thread_id": f"fixture-thread-{cell_id}"},
                    {"type": "turn.started"},
                    {"type": "item.started", "item": {"id": "message-1", "type": "agent_message", "text": ""}},
                    {"type": "item.completed", "item": {"id": "message-1", "type": "agent_message", "text": final}},
                    {"type": "turn.completed", "usage": {"input_tokens": 4, "output_tokens": 4}},
                )
            )
            events_path = responses / "batch-0001.attempt-0001.events.jsonl"
            message_path = responses / "batch-0001.attempt-0001.message.json"
            stderr_path = root / "raw-codex-stderr.bin"
            events_path.write_bytes(events)
            message_path.write_text(final, encoding="utf-8")
            stderr_path.write_bytes(b"")
            contacts.append(cell_id)
            native = load(NATIVE, "v14_sol_native_fixture")
            return final, {
                "command": native._expected_codex_command(kwargs["executable"], root),
                "reported": {"model": None, "provider": None, "reasoning_effort": None, "session_id": f"fixture-thread-{cell_id}"},
                "provider_artifacts": {
                    "codex_events": {"path": events_path.relative_to(root).as_posix(), "bytes": len(events), "sha256": value.sha256(events)},
                    "codex_stderr": {"path": stderr_path.relative_to(root).as_posix(), "bytes": 0, "sha256": value.sha256(b"")},
                },
            }
        finally:
            with lock:
                concurrency["active"] -= 1

    return invoke


def test_direct_frozen_eight_schedule_has_no_grok_receipt_prerequisite(value: tuple[Any, Any], tmp_path: Path):
    module, study = value
    args = common(tmp_path, study)
    resolution = module._resolution(**resolution_args(args))
    schedule = study.schedule(**resolution_args(args))
    source = {(row["candidate_id"], row["item_id"]): row for row in schedule["cells"]}
    assert len(resolution["rows"]) == len(source) == 8
    assert {row["candidate_id"] for row in resolution["rows"]} == {module.CHILD20, module.DESCENDANT}
    assert {row["partition"] for row in resolution["rows"]} == {"train"}
    for row in resolution["rows"]:
        original = source[(row["candidate_id"], row["item_id"])]
        payload = base64.b64decode(row["payload_base64"], validate=True)
        assert row["payload_base64"] == original["payload_base64"]
        assert row["payload_sha256"] == module.sha256(payload)
        assert original["endpoint_payload_sha256s"]["grok_primary"] == original["endpoint_payload_sha256s"]["sol_later"] == row["payload_sha256"]
        assert "target" not in json.loads(payload)
    assert "import dspy" not in SOL.read_text(encoding="utf-8").lower()


def test_prepare_eight_is_provider_free_and_uses_no_grok_result(value: tuple[Any, Any], tmp_path: Path):
    module, study = value
    args = common(tmp_path, study)
    result = module.prepare_all(**{name: item for name, item in args.items() if name != "route_evidence"})
    assert result == {
        "study_id": module.STUDY_ID,
        "state": "prepared_exact_8_matched_sol_train_cells",
        "cells": 8,
        "groups": 4,
        "provider_calls_made": 0,
        "process_launches": 0,
        "max_concurrency": 8,
    }
    assert len(list(args["output_root"].iterdir())) == 8


def test_prepare_rejects_output_inside_each_immutable_source_parent_before_write(value: tuple[Any, Any], tmp_path: Path):
    module, study = value
    args = common(tmp_path, study)
    protected_files = (SPLIT, CSV, CONTRACT, study.RECOVERED)
    for index, protected in enumerate(protected_files):
        overlap = Path(protected).parent / f"v14-sol-overlap-{tmp_path.name}-{index}"
        assert not overlap.exists()
        with pytest.raises(ValueError):
            module.prepare_all(**{**{name: item for name, item in args.items() if name != "route_evidence"}, "output_root": overlap})
        assert not overlap.exists()


def test_sol_eight_uses_one_callback_per_receipt_and_independent_mae(value: tuple[Any, Any], tmp_path: Path):
    module, study = value
    args = common(tmp_path, study)
    call_args = {name: item for name, item in args.items() if name != "route_evidence"}
    module.prepare_all(**call_args)
    rows = module._resolution(**resolution_args(args))["rows"]
    contacts: list[str] = []
    concurrency = {"active": 0, "maximum": 0}
    results = module.execute_wave(**call_args, allow_remote=True, call_codex=fake_codex(module, rows, contacts, concurrency))
    assert len(results) == len(contacts) == 8 and 1 <= concurrency["maximum"] <= 8
    report = module.report(**report_args(args))
    assert (report["endpoint"], report["partition"]) == ("sol_later", "train")
    assert len(report["cells"]) == report["unique_thread_ids"] == report["unique_session_ids"] == 8
    assert all(all(math.isfinite(cell["scores"][name]) and type(cell["coverage"][name]) is bool for name in module.DIMS) for cell in report["cells"])
    assert any(all(cell["scores"][name] == 0.0 and cell["coverage"][name] is False for name in module.DIMS) for cell in report["cells"])
    expected = {}
    for candidate in (module.CHILD20, module.DESCENDANT):
        errors = [cell["per_item_mae"] for cell in report["cells"] if cell["candidate_id"] == candidate]
        expected[candidate] = sum(errors) / len(errors)
    assert {row["candidate_id"]: row["equal_group_mean_item_mae"] for row in report["metrics"]} == pytest.approx(expected)
    assert all(row["item_count"] == row["group_count"] == 4 and len(row["per_group_mean_item_mae"]) == 4 for row in report["metrics"])
    before = {path.relative_to(args["output_root"]).as_posix(): path.read_bytes() for path in args["output_root"].rglob("*") if path.is_file()}
    with pytest.raises(ValueError, match="resend|terminal|inventory"):
        module.execute_wave(**call_args, allow_remote=True, call_codex=lambda **_kwargs: pytest.fail("replay contacted Sol"))
    assert {path.relative_to(args["output_root"]).as_posix(): path.read_bytes() for path in args["output_root"].rglob("*") if path.is_file()} == before
