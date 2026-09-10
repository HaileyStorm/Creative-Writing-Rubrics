from __future__ import annotations

import importlib.util
import json
import shutil
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
EVAL = ROOT / "evaluation-results" / "hbq-human-alignment-dryad-full-hbq-analysis-v1"
PARENT_ROOT = Path(r"C:\Users\Haile\Documents\cwr-dryad-sol-selected100-recovery-20260910-r1")
PLAN_ROOT = Path(r"C:\Users\Haile\Documents\cwr-dryad-baseline8-plan-20260906-r1")


def load(name: str) -> Any:
    spec = importlib.util.spec_from_file_location(f"test_{name}", EVAL / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def fixture() -> tuple[Any, Any, Any, dict[str, Any], Path, dict[str, Any], dict[str, Any]]:
    validator, parent = load("sol_retained_completion"), load("sol_selected_recovery_execution")
    old = parent._load(parent.OLD, parent.OLD_SHA256, "test frozen collector")
    runtime = parent._load(parent.RUNTIME, parent.RUNTIME_SHA256, "test frozen runtime")
    request, _prompt, _schema = parent._request(old, PLAN_ROOT, 4486)
    slot = PARENT_ROOT / "requests" / "4486"
    route = parent._json(slot / "route.json", "route")
    source = parent._json(slot / "source-bindings.json", "source")
    return validator, parent, runtime, request, slot, route, source


def test_real_retained_completed_message_is_recognized_without_process_success() -> None:
    validator, _parent, runtime, request, slot, route, source = fixture()
    content, thread_id, record = validator.validate_completed_unknown_exit(
        slot=slot, request=request, frozen_runtime=runtime, route=route, source=source)

    assert content
    assert thread_id == record["native_thread_id"]
    assert record["completion_class"] == "completed_with_unknown_exit"
    assert record["process_success_proven"] is False


@pytest.mark.parametrize("mutation", ["missing_message", "nonzero", "tool_lifecycle", "conflicting_label"])
def test_retained_validator_rejects_missing_or_noncanonical_completion(tmp_path: Path, mutation: str) -> None:
    validator, _parent, runtime, request, slot, route, source = fixture()
    copied = tmp_path / "slot"; shutil.copytree(slot, copied)
    message = copied / "native-output" / "responses" / "batch-0001.attempt-0001.message.json"
    receipt_path = copied / "process-completion" / "native-output.json"
    if mutation == "missing_message":
        message.unlink()
    elif mutation == "nonzero":
        receipt = json.loads(receipt_path.read_text(encoding="utf-8")); receipt["exit_code"] = 1
        receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    elif mutation == "tool_lifecycle":
        events = copied / "native-output" / "responses" / "batch-0001.attempt-0001.events.jsonl"
        rows = events.read_text(encoding="utf-8").splitlines(); rows.insert(2, json.dumps({"type": "item.completed", "item": {"type": "function_call"}}))
        events.write_text("\n".join(rows) + "\n", encoding="utf-8")
    else:
        stderr = copied / "native-output" / "responses" / "batch-0001.attempt-0001.stderr.bin"
        stderr.write_text("model: another-model\n", encoding="utf-8")

    with pytest.raises(ValueError):
        validator.validate_completed_unknown_exit(slot=copied, request=request, frozen_runtime=runtime, route=route, source=source)


def test_reconciliation_record_binds_all_retained_native_artifacts() -> None:
    validator, _parent, runtime, request, slot, route, source = fixture()
    reconciliation = json.loads(Path(r"C:\Users\Haile\Documents\cwr-dryad-sol-completed-message-recovery-4486-4492-20260910-r1\reconciliation.json").read_text(encoding="utf-8"))
    record = next(item for item in reconciliation["recoveries"] if item["ordinal"] == 4486)
    _content, _thread, accepted = validator.validate_completed_unknown_exit(
        slot=slot, request=request, frozen_runtime=runtime, route=route, source=source, expected_record=record)

    assert accepted["provider_attested"] is False
