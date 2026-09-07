from __future__ import annotations

import importlib.util
import json
import subprocess
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "evaluation-results/hbq-human-alignment-wpb-compact-family-native-v1/sol_batched_execution.py"
SUPPORT = Path(__file__).with_name("test_hbq_human_alignment_wpb_compact_native_v1.py")
FREEZE_ROOT = Path(r"C:\Users\Haile\Documents\cwr-wpb-pilot-source-freeze-20260904-r3")
VERIFIER_SHA256 = "e" * 64


def load(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def context(value: Any) -> dict[str, Any]:
    resolution = value._frozen()._resolution(freeze_root=FREEZE_ROOT)
    return {
        "freeze_sha256": "f" * 64,
        "selection_frozen_at": "2026-09-07T00:00:00Z",
        "selected_profile": {"core": 1.0, "craft": 1.0, "form": 1.0},
        "schedule_sha256": resolution["schedule_sha256"],
        "source_bindings": {"fixture": "synthetic_only"},
        "evidence_files": {"fixture": "synthetic_only"},
        "native_measurement_count": 129,
    }


def install_freeze(monkeypatch: pytest.MonkeyPatch, value: Any, frozen: dict[str, Any]) -> None:
    def verify(path: Path, expected: str, *, replay_native: bool) -> dict[str, Any]:
        assert path.name == "grok-selection-freeze.json" and expected == frozen["freeze_sha256"]
        return dict(frozen)

    monkeypatch.setattr(value, "_freeze_module", lambda expected: SimpleNamespace(verify_freeze=verify))


def review(value: Any, path: Path, *, campaign_sha256: str, cell_ids: list[str], route_sha256: str) -> str:
    now = datetime.now(timezone.utc)
    record = {
        "format_version": 1,
        "kind": "approved_wpb_sol_batched_dispatch",
        "decision": "approved_wpb_sol_batched_dispatch",
        "campaign_sha256": campaign_sha256,
        "batch_number": 1,
        "cell_ids": cell_ids,
        "freeze_sha256": "f" * 64,
        "route_sha256": route_sha256,
        "reviewed_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "expires_at": (now + timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    path.write_bytes(value.canonical(record))
    return value.sha256(path.read_bytes())


def freeze_review(value: Any, path: Path) -> str:
    path.write_bytes(value.canonical({
        "format_version": 1,
        "kind": "wpb_grok_selection_freeze_independent_review",
        "freeze_sha256": "f" * 64,
        "freeze_verifier_sha256": VERIFIER_SHA256,
        "decision": "approved_wpb_grok_selection_freeze",
        "reviewed_at": "2026-09-07T00:00:00Z",
    }))
    return value.sha256(path.read_bytes())


def fresh_route(route: dict[str, Any]) -> dict[str, Any]:
    value = {**route, "cost_evidence": dict(route["cost_evidence"])}
    value["cost_evidence"].update({
        "checked_at": (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat(),
        "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=30)).isoformat(),
    })
    return value


def test_one_batched_epoch_uses_actual_sol_wrapper_and_frozen_admission(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    value = load(HELPER, "wpb_sol_wrapper_integration")
    support = load(SUPPORT, "wpb_sol_wrapper_integration_support")
    frozen = context(value)
    install_freeze(monkeypatch, value, frozen)
    campaign, queue = tmp_path / "external-campaign", tmp_path / "queue"
    queue.mkdir()
    freeze_path = tmp_path / "grok-selection-freeze.json"
    freeze_approval = tmp_path / "freeze-review.json"
    created = value.create_campaign(
        campaign_root=campaign,
        queue_root=queue,
        freeze_root=FREEZE_ROOT,
        freeze_path=freeze_path,
        expected_freeze_sha256=frozen["freeze_sha256"],
        expected_freeze_verifier_sha256=VERIFIER_SHA256,
        independent_review_path=freeze_approval,
        expected_independent_review_sha256=freeze_review(value, freeze_approval),
    )
    route_support = support.load(support.V12_TEST, "wpb_sol_wrapper_integration_route_support")
    route, _evidence = route_support.sol_route()
    route = fresh_route(route)
    resolution = value._frozen()._resolution(freeze_root=FREEZE_ROOT)
    cell_ids = [str(row["cell_id"]) for row in resolution["rows"][:10]]
    approval = tmp_path / "batch-review.json"
    prepared = value.prepare_next_batch(
        campaign_root=campaign,
        queue_root=queue,
        freeze_root=FREEZE_ROOT,
        freeze_path=freeze_path,
        expected_freeze_sha256=frozen["freeze_sha256"],
        expected_freeze_verifier_sha256=VERIFIER_SHA256,
        review_path=approval,
        expected_review_sha256=review(value, approval, campaign_sha256=created["campaign_sha256"], cell_ids=cell_ids,
                                      route_sha256=value.sha256(route)),
        authorization_acknowledgement_sha256="a" * 64,
        broker_factory=lambda _root: route_support.Broker(route),
    )
    assert prepared["prepared_cells"] == cell_ids
    commands: list[list[str]] = []
    lock = threading.Lock()
    original_run = subprocess.run

    def fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[bytes]:
        if "input" not in kwargs:
            return original_run(command, **kwargs)
        prompt = kwargs["input"]
        assert isinstance(prompt, bytes)
        json.loads(prompt)
        message = Path(command[command.index("--output-last-message") + 1])
        root = message.parents[1]
        final = json.dumps(support.answer(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        events = b"".join(
            json.dumps(event, ensure_ascii=False, separators=(",", ":")).encode("utf-8") + b"\n"
            for event in (
                {"type": "thread.started", "thread_id": f"fixture-thread-{root.name}"},
                {"type": "turn.started"},
                {"type": "item.started", "item": {"id": "message-1", "type": "agent_message", "text": ""}},
                {"type": "item.completed", "item": {"id": "message-1", "type": "agent_message", "text": final}},
                {"type": "turn.completed", "usage": {"input_tokens": 4, "output_tokens": 4}},
            )
        )
        message.write_text(final, encoding="utf-8")
        with lock:
            commands.append(list(command))
        return subprocess.CompletedProcess(command, 0, stdout=events, stderr=b"")

    monkeypatch.setattr(subprocess, "run", fake_run)
    outcomes = value.dispatch_batch(
        campaign_root=campaign,
        queue_root=queue,
        freeze_root=FREEZE_ROOT,
        freeze_path=freeze_path,
        expected_freeze_sha256=frozen["freeze_sha256"],
        expected_freeze_verifier_sha256=VERIFIER_SHA256,
        batch_number=1,
        allow_remote=True,
        broker_factory=lambda _root: route_support.Broker(route),
    )
    settled = value.settle_batch(
        campaign_root=campaign,
        freeze_root=FREEZE_ROOT,
        freeze_path=freeze_path,
        expected_freeze_sha256=frozen["freeze_sha256"],
        expected_freeze_verifier_sha256=VERIFIER_SHA256,
        batch_number=1,
    )
    assert len(outcomes) == len(commands) == 10
    assert settled["status"] == "completed" and settled["completed_cells"] == cell_ids
    assert all(command[-1] == "-" for command in commands)
    assert all(command[command.index("code_mode") - 1:command.index("code_mode") + 1] == ["--disable", "code_mode"] for command in commands)
    for cell_id in cell_ids:
        root = campaign / "batches/0001/execution" / cell_id
        assert (root / "execution-receipt.json").is_file()
        assert (root / "raw-codex-events.bin").is_file()
