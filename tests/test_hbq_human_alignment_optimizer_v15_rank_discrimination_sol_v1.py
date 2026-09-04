from __future__ import annotations

"""Regression coverage for the separate V15 Sol measurement surface."""

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
PACKAGE = ROOT / "evaluation-results" / "hbq-human-alignment-optimizer-v15-rank-discrimination-v1"
SOL = PACKAGE / "sol.py"
STUDY = PACKAGE / "study.py"
NATIVE = ROOT / "evaluation-results" / "hbq-human-alignment-optimizer-v4-native-subscription-exec-v3" / "executor.py"
V12_TEST = ROOT / "tests" / "test_hbq_human_alignment_optimizer_v12_development_sol_exec_v1.py"
SPLIT = Path(r"C:\Users\Haile\Documents\cwr-hanna-optimizer-grok-primary-dev-20260829-d189d71\split-manifest.json")
CSV = Path(r"C:\Users\Haile\Documents\cwr-hanna-pinned-data-282f275\hanna_stories_annotations.csv")
CONTRACT = Path(r"C:\Users\Haile\Documents\cwr-hanna-successor-fresh88-freeze-v4\frozen-successor-contract.json")
ACK = "a" * 64


def load(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


@pytest.fixture
def value() -> tuple[Any, Any]:
    return load(SOL, "v15_rank_discrimination_sol"), load(STUDY, "v15_rank_discrimination_grok_fixture")


def common(tmp_path: Path) -> dict[str, Any]:
    support = load(V12_TEST, "v15_rank_discrimination_sol_support")
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
        "broker_factory": lambda _root: support.Broker(route),
        "route_evidence": evidence,
    }


def resolution_args(args: dict[str, Any]) -> dict[str, Any]:
    return {name: args[name] for name in ("split_manifest", "hanna_csv", "successor_contract")}


def report_args(args: dict[str, Any]) -> dict[str, Any]:
    return {name: args[name] for name in ("output_root", "authorization_acknowledgement_sha256", "split_manifest", "hanna_csv", "successor_contract")}


def fake_codex(
    value: Any,
    rows: tuple[dict[str, Any], ...],
    contacts: list[str],
    concurrency: dict[str, int],
    wrong_shape_cell: str | None = None,
):
    by_cell = {row["cell_id"]: row for row in rows}
    lock = threading.Lock()

    def invoke(**kwargs: Any):
        root = Path(kwargs["output_dir"])
        row = by_cell[root.name]
        with lock:
            concurrency["active"] += 1
            concurrency["maximum"] = max(concurrency["maximum"], concurrency["active"])
        try:
            time.sleep(0.002)
            evidence = {name: "Fixture evidence is present." for name in value.DIMS}
            coverage = {name: False for name in value.DIMS}
            if row["condition"] == value.THRESHOLDS or row["cell_id"] == wrong_shape_cell:
                bits = {name: {key: False for key in ("at_least_2", "at_least_3", "at_least_4", "at_least_5")} for name in value.DIMS}
                answer = {"thresholds": bits, "evidence": evidence, "coverage": coverage}
            else:
                answer = {"scores": {name: 3 for name in value.DIMS}, "evidence": evidence, "coverage": coverage}
            final = json.dumps(answer, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            responses = root / "responses"
            responses.mkdir(exist_ok=True)
            kwargs["before_provider_attempt"]()
            events = b"".join(
                json.dumps(event, ensure_ascii=False, separators=(",", ":")).encode("utf-8") + b"\n"
                for event in (
                    {"type": "thread.started", "thread_id": f"fixture-thread-{row['cell_id']}"},
                    {"type": "turn.started"},
                    {"type": "item.started", "item": {"id": "message-1", "type": "agent_message", "text": ""}},
                    {"type": "item.completed", "item": {"id": "message-1", "type": "agent_message", "text": final}},
                    {"type": "turn.completed", "usage": {"input_tokens": 4, "output_tokens": 4}},
                )
            )
            events_path = responses / "batch-0001.attempt-0001.events.jsonl"
            stderr_path = root / "raw-codex-stderr.bin"
            events_path.write_bytes(events)
            (responses / "batch-0001.attempt-0001.message.json").write_text(final, encoding="utf-8")
            stderr_path.write_bytes(b"")
            contacts.append(row["cell_id"])
            native = load(NATIVE, "v15_rank_discrimination_native_fixture")
            return final, {
                "command": native._expected_codex_command(kwargs["executable"], root),
                "reported": {"model": None, "provider": None, "reasoning_effort": None, "session_id": f"fixture-thread-{row['cell_id']}"},
                "provider_artifacts": {
                    "codex_events": {"path": events_path.relative_to(root).as_posix(), "bytes": len(events), "sha256": value._base().sha256(events)},
                    "codex_stderr": {"path": stderr_path.relative_to(root).as_posix(), "bytes": 0, "sha256": value._base().sha256(b"")},
                },
            }
        finally:
            with lock:
                concurrency["active"] -= 1

    return invoke


def test_schedule_is_exact_96_grok_payload_parity_without_outbound_targets(value: tuple[Any, Any], tmp_path: Path):
    module, study = value
    args = common(tmp_path)
    resolution = module._resolution(**resolution_args(args))
    schedule = study.schedule(**resolution_args(args))
    source = {row["cell_id"]: row for row in schedule["cells"]}
    assert len(resolution["rows"]) == len(source) == 96
    assert {row["condition"] for row in resolution["rows"]} == {module.DIRECT, module.THRESHOLDS}
    assert len({row["item_id"] for row in resolution["rows"]}) == 48
    assert len({row["prompt_group_id"] for row in resolution["rows"]}) == 24
    for row in resolution["rows"]:
        original = source[row["source_cell_id"]]
        payload = base64.b64decode(row["payload_base64"], validate=True)
        assert row["payload_base64"] == original["payload_base64"]
        assert row["payload_sha256"] == module._base().sha256(payload)
        assert original["endpoint_payload_sha256s"] == {"grok_primary": row["payload_sha256"], "sol_later": row["payload_sha256"]}
        assert "target" not in json.loads(payload)
    source_text = SOL.read_text(encoding="utf-8").lower()
    assert "import dspy" not in source_text and "import optuna" not in source_text


def test_prepare_is_provider_free_and_records_requested_not_attested_sol_identity(value: tuple[Any, Any], tmp_path: Path):
    module, _study = value
    args = common(tmp_path)
    call_args = {name: item for name, item in args.items() if name != "route_evidence"}
    assert module.prepare_all(**call_args) == {
        "study_id": module.STUDY_ID,
        "state": "prepared_exact_96_matched_sol_train_cells",
        "cells": 96,
        "groups": 24,
        "provider_calls_made": 0,
        "process_launches": 0,
        "max_concurrency": 10,
    }
    roots = sorted(path for path in args["output_root"].iterdir() if path.is_dir())
    assert len(roots) == 96
    for root in roots:
        prepared = json.loads((root / "prepared.json").read_text(encoding="utf-8"))
        payload = (root / "outbound-payload.json").read_bytes()
        assert module._base().sha256(payload) == prepared["task_payload_sha256"]
        assert "target" not in json.loads(payload)
        assert (root / "execution-receipt.json").exists() is False
    for index, protected in enumerate((SPLIT, CSV, CONTRACT)):
        overlap = protected.parent / f"v15-sol-overlap-{tmp_path.name}-{index}"
        assert not overlap.exists()
        with pytest.raises(ValueError):
            module.prepare_all(**{**call_args, "output_root": overlap})
        assert not overlap.exists()


def test_native_receipts_project_all_false_thresholds_and_refuse_resends(value: tuple[Any, Any], tmp_path: Path):
    module, _study = value
    args = common(tmp_path)
    call_args = {name: item for name, item in args.items() if name != "route_evidence"}
    module.prepare_all(**call_args)
    rows = module._resolution(**resolution_args(args))["rows"]
    contacts: list[str] = []
    concurrency = {"active": 0, "maximum": 0}
    results = module.execute_wave(**call_args, allow_remote=True, call_codex=fake_codex(module, rows, contacts, concurrency))
    assert len(results) == len(contacts) == 96 and 1 <= concurrency["maximum"] <= 10
    receipt_roots = sorted(path for path in args["output_root"].iterdir() if path.is_dir())
    for root in receipt_roots:
        receipt = json.loads((root / "execution-receipt.json").read_text(encoding="utf-8"))
        settings = json.loads((root / "effective-settings.json").read_text(encoding="utf-8"))
        assert (root / "raw-codex-events.bin").is_file() and (root / "raw-codex-final-response.bin").is_file()
        assert receipt["identity"]["requested_model"] == settings["requested_model"] == "gpt-5.6-sol"
        assert receipt["identity"]["requested_reasoning_effort"] == settings["requested_reasoning_effort"] == "high"
        assert receipt["identity"]["provider_reported_model"] is None and settings["provider_attested"] is False
    report = module.report(**report_args(args))
    assert report["endpoint"] == "sol_later" and report["status"] == "complete_matched_96_cells"
    assert len(report["cells"]) == report["unique_thread_ids"] == report["unique_session_ids"] == 96
    threshold_cells = [cell for cell in report["cells"] if cell["condition"] == module.THRESHOLDS]
    assert len(threshold_cells) == 48
    assert all(
        all(
            cell["raw_threshold_bits"][dimension][key] is False
            for dimension in module.DIMS
            for key in ("at_least_2", "at_least_3", "at_least_4", "at_least_5")
        )
        and all(cell["scores"][dimension] == 1.0 and cell["coverage"][dimension] is False for dimension in module.DIMS)
        for cell in threshold_cells
    )
    direct_cells = [cell for cell in report["cells"] if cell["condition"] == module.DIRECT]
    assert all(all(cell["scores"][dimension] == 3.0 for dimension in module.DIMS) for cell in direct_cells)
    assert all(all(math.isfinite(cell["scores"][dimension]) for dimension in module.DIMS) for cell in report["cells"])
    assert all(len(cell["final_response_sha256"]) == len(cell["receipt_sha256"]) == 64 for cell in report["cells"])
    before = {path.relative_to(args["output_root"]).as_posix(): path.read_bytes() for path in args["output_root"].rglob("*") if path.is_file()}
    with pytest.raises(ValueError, match="resend|terminal|inventory"):
        module.execute_wave(**call_args, allow_remote=True, call_codex=lambda **_kwargs: pytest.fail("replay contacted Sol"))
    assert {path.relative_to(args["output_root"]).as_posix(): path.read_bytes() for path in args["output_root"].rglob("*") if path.is_file()} == before


def test_native_response_shape_is_bound_to_each_v15_condition(value: tuple[Any, Any], tmp_path: Path):
    module, _study = value
    args = common(tmp_path)
    call_args = {name: item for name, item in args.items() if name != "route_evidence"}
    resolution = module._resolution(**resolution_args(args))
    rows = tuple(next(row for row in resolution["rows"] if row["condition"] == condition) for condition in (module.DIRECT, module.THRESHOLDS))
    limited = dict(resolution)
    limited["rows"] = rows
    original = module._resolution
    module._resolution = lambda **_kwargs: limited
    try:
        module.prepare_all(**call_args)
        module.execute_wave(
            **call_args,
            allow_remote=True,
            call_codex=fake_codex(module, rows, [], {"active": 0, "maximum": 0}, rows[0]["cell_id"]),
        )
        with pytest.raises(ValueError, match="direct 1-5 answer"):
            module.report(**report_args(args))
    finally:
        module._resolution = original
