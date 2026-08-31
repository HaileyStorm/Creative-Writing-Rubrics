from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "evaluation-results" / "hbq-human-alignment-optimizer-v5-f20-confirmation-sol-reconcile-v2-existing-output"


def module():
    spec = importlib.util.spec_from_file_location("_confirmation_sol_reconcile_v2", PACKAGE / "verify.py")
    assert spec and spec.loader
    value = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = value
    spec.loader.exec_module(value)
    return value


def test_terminal_multiple_agent_messages_remain_excluded(tmp_path: Path):
    value = module()
    root = tmp_path / "cell"; responses = root / "responses"
    responses.mkdir(parents=True)
    for name, raw in {
        "outbound-payload.json": b"{}\n", "response-schema.json": b"{}\n", "target-vector.json": b"{}\n",
        "disclosure.json": b"{}\n", "authorization-acknowledgement.json": b"{}\n", "zero-charge-route-proof.json": b"{}\n",
        "prepared.json": b"{}\n", "launch-intent.json": b"{}\n", "raw-codex-stderr.bin": b"",
        "result.json": value.canonical({"format_version": 1, "study_id": "fixture", "kind": "reconcile_required_after_process_launch", "cell_id": "cell", "process_launches": 1, "provider_calls_made": None, "error_type": "ValueError"}),
    }.items():
        (root / name).write_bytes(raw)
    (responses / "batch-0001.attempt-0001.events.jsonl").write_bytes(b'{"item":"first"}\n{"item":"second"}\n')
    (responses / "batch-0001.attempt-0001.message.json").write_bytes(b"{}")
    class Base: STUDY_ID = "fixture"
    class V3:
        @staticmethod
        def _load_parse_codex_events(): return object()
        @staticmethod
        def _codex_event_projection(_events, _parser): raise ValueError("HANNA native exec Codex JSONL must complete exactly one agent message")
    assert value._invalid_terminal(root, {"cell_id": "cell"}, Base(), V3()) == "HANNA native exec Codex JSONL must complete exactly one agent message"


def test_terminal_that_becomes_projectable_is_rejected(tmp_path: Path):
    value = module()
    root = tmp_path / "cell"; responses = root / "responses"
    responses.mkdir(parents=True)
    for name, raw in {
        "outbound-payload.json": b"{}\n", "response-schema.json": b"{}\n", "target-vector.json": b"{}\n",
        "disclosure.json": b"{}\n", "authorization-acknowledgement.json": b"{}\n", "zero-charge-route-proof.json": b"{}\n",
        "prepared.json": b"{}\n", "launch-intent.json": b"{}\n", "raw-codex-stderr.bin": b"",
        "result.json": value.canonical({"format_version": 1, "study_id": "fixture", "kind": "reconcile_required_after_process_launch", "cell_id": "cell", "process_launches": 1, "provider_calls_made": None, "error_type": "ValueError"}),
    }.items():
        (root / name).write_bytes(raw)
    (responses / "batch-0001.attempt-0001.events.jsonl").write_bytes(b"{}\n")
    (responses / "batch-0001.attempt-0001.message.json").write_bytes(b"{}")
    class Base: STUDY_ID = "fixture"
    class V3:
        @staticmethod
        def _load_parse_codex_events(): return object()
        @staticmethod
        def _codex_event_projection(_events, _parser): return {"completed_agent_message_text": "{}"}
    with pytest.raises(ValueError, match="unexpectedly became projectable"):
        value._invalid_terminal(root, {"cell_id": "cell"}, Base(), V3())


def test_committed_v1_is_loaded_and_reconcile_has_no_optimizer_runtime():
    value = module()
    source = (PACKAGE / "verify.py").read_text(encoding="utf-8").lower()
    assert "import dspy" not in source and "import optuna" not in source
    assert value._load_v1().STUDY_ID == "hbq-human-alignment-optimizer-v5-f20-confirmation-sol-exec-v1"
