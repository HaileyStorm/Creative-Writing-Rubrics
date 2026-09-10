from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "evaluation-results/hbq-human-alignment-wpb-compact-family-native-v1/sol_strict_schema_successor.py"
SUPPORT = ROOT / "tests/test_hbq_human_alignment_wpb_compact_native_v1.py"
FREEZE_ROOT = Path(r"C:\Users\Haile\Documents\cwr-wpb-pilot-source-freeze-20260904-r3")
BASE = Path(r"C:\Users\Haile\Documents\cwr-wpb-sol-batched-validation-20260910-r1")
VERIFIER_SHA256_PLACEHOLDER = "e" * 64


def load(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def subject() -> Any:
    return load(SOURCE, "wpb_sol_strict_schema_successor_test")


def support() -> Any:
    return load(SUPPORT, "wpb_sol_strict_schema_successor_support")


def write(path: Path, value: Any) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8") + b"\n")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verifier(tmp_path: Path, value: Any) -> tuple[Path, str, dict[str, Any]]:
    resolution = value._configured_legacy()[0]._frozen()._resolution(freeze_root=FREEZE_ROOT)
    context = {
        "freeze_sha256": "f" * 64,
        "selection_frozen_at": "2026-09-07T00:00:00Z",
        "selected_profile": {"core": 1.0, "craft": 1.0, "form": 1.0},
        "schedule_sha256": resolution["schedule_sha256"],
        "source_bindings": {"fixture": "strict-successor"},
        "evidence_files": {"fixture": "strict-successor"},
        "native_measurement_count": 129,
    }
    path = tmp_path / "fixture-freeze-verifier.py"
    path.write_text("def verify_freeze(_path, _expected, *, replay_native):\n    return " + repr(context) + "\n", encoding="utf-8")
    return path, hashlib.sha256(path.read_bytes()).hexdigest(), context


def freeze_review(tmp_path: Path, value: Any, context: dict[str, Any], verifier_sha: str) -> tuple[Path, str]:
    path = tmp_path / "freeze-review.json"
    digest = write(path, {"format_version": 1, "kind": "wpb_grok_selection_freeze_independent_review",
                          "decision": "approved_wpb_grok_selection_freeze", "freeze_sha256": context["freeze_sha256"],
                          "freeze_verifier_sha256": verifier_sha, "reviewed_at": "2026-09-07T00:00:00Z"})
    return path, digest


def fresh_route(route: dict[str, Any]) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    return {**route, "cost_evidence": {**route["cost_evidence"], "checked_at": (now - timedelta(seconds=1)).isoformat(),
                                         "expires_at": (now + timedelta(minutes=30)).isoformat()}}


def create(value: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path, dict[str, Any], Any, dict[str, Any]]:
    verifier_path, verifier_sha, context = verifier(tmp_path, value)
    approval, approval_sha = freeze_review(tmp_path, value, context, verifier_sha)
    campaign, queue = tmp_path / "campaign", tmp_path / "queue"; queue.mkdir()
    result = value.create_campaign(campaign_root=campaign, base_campaign_path=BASE / "campaign.json",
                                   reconciliation_path=BASE / "first-batch-reconciliation-20260910-r1.json", queue_root=queue,
                                   freeze_root=FREEZE_ROOT, freeze_path=tmp_path / "grok-selection-freeze.json",
                                   expected_freeze_sha256=context["freeze_sha256"], expected_freeze_verifier_sha256=verifier_sha,
                                   independent_review_path=approval, expected_independent_review_sha256=approval_sha,
                                   freeze_verifier_path=verifier_path)
    helper = support()
    route_support = helper.load(helper.V12_TEST, "wpb_sol_strict_schema_route_support")
    return campaign, queue, result, route_support, {"context": context, "verifier": verifier_path, "verifier_sha": verifier_sha}


def prepare(value: Any, campaign: Path, queue: Path, route_support: Any, state: dict[str, Any], epoch: int = 1) -> tuple[dict[str, Any], dict[str, Any]]:
    route = fresh_route(route_support.sol_route()[0])
    legacy_campaign = json.loads((campaign / "campaign.json").read_bytes())
    completed = {cell["cell_id"] for path in (campaign / "batches").glob("*/settlement.json") for cell in json.loads(path.read_bytes())["cells"] if cell["state"] == "completed"}
    ids = [cell["cell_id"] for cell in legacy_campaign["cells"] if cell["cell_id"] not in completed][:10]
    review_path = campaign.parent / f"legacy-review-{epoch:04d}.json"
    now = datetime.now(timezone.utc)
    review_sha = write(review_path, {"format_version": 1, "kind": "approved_wpb_sol_batched_dispatch",
                                     "decision": "approved_wpb_sol_batched_dispatch", "campaign_sha256": hashlib.sha256((campaign / "campaign.json").read_bytes()).hexdigest(),
                                     "batch_number": epoch, "cell_ids": ids, "freeze_sha256": state["context"]["freeze_sha256"],
                                     "route_sha256": value.sha256(route), "reviewed_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
                                     "expires_at": (now + timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%SZ")})
    prepared = value.prepare_next_batch(campaign_root=campaign, queue_root=queue, freeze_root=FREEZE_ROOT,
                                        freeze_path=campaign.parent / "grok-selection-freeze.json", expected_freeze_sha256=state["context"]["freeze_sha256"],
                                        expected_freeze_verifier_sha256=state["verifier_sha"], freeze_verifier_path=state["verifier"],
                                        review_path=review_path, expected_review_sha256=review_sha, authorization_acknowledgement_sha256="a" * 64,
                                        broker_factory=lambda _root: route_support.Broker(route))
    return prepared, route


def strict_review(value: Any, campaign: Path, number: int, *, expires_at: datetime | None = None) -> tuple[Path, str]:
    material = value.review_material(campaign_root=campaign, batch_number=number)
    now = datetime.now(timezone.utc); expiry = expires_at or now + timedelta(hours=2)
    path = campaign.parent / f"strict-review-{number:04d}.json"
    return path, write(path, {**material, "reviewed_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "expires_at": expiry.strftime("%Y-%m-%dT%H:%M:%SZ")})


def synthetic_subprocess(value: Any, monkeypatch: pytest.MonkeyPatch, calls: list[list[str]], *, fail: bool = False) -> None:
    lock = threading.Lock()
    original_run = subprocess.run

    def run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[bytes]:
        if "input" not in kwargs:
            return original_run(command, **kwargs)
        assert kwargs["input"] and command[-1] == "-"
        root = Path(command[command.index("--cd") + 1]); strict = Path(command[command.index("--output-schema") + 1])
        original = json.loads((root / "response-schema.json").read_bytes()); projected = json.loads(strict.read_bytes())
        assert projected == value.strict_native_schema(original)
        message = Path(command[command.index("--output-last-message") + 1])
        answer = support().answer(value); final = json.dumps(answer, sort_keys=True, separators=(",", ":"))
        message.parent.mkdir(parents=True, exist_ok=True); message.write_text(final, encoding="utf-8")
        events = b"".join(json.dumps(event, separators=(",", ":")).encode() + b"\n" for event in (
            {"type": "thread.started", "thread_id": f"fixture-thread-{root.name}"}, {"type": "turn.started"},
            {"type": "item.started", "item": {"id": "message", "type": "agent_message", "text": ""}},
            {"type": "item.completed", "item": {"id": "message", "type": "agent_message", "text": final}},
            {"type": "turn.completed", "usage": {"input_tokens": 3, "output_tokens": 3}},
        ))
        with lock:
            calls.append(list(command))
            code = 1 if fail and len(calls) == 1 else 0
        return subprocess.CompletedProcess(command, code, stdout=events, stderr=b"")

    monkeypatch.setattr(subprocess, "run", run)


def dispatch(value: Any, campaign: Path, queue: Path, route_support: Any, state: dict[str, Any], route: dict[str, Any], number: int, review: tuple[Path, str]) -> list[dict[str, Any]]:
    return value.dispatch_batch(campaign_root=campaign, queue_root=queue, freeze_root=FREEZE_ROOT,
                                freeze_path=campaign.parent / "grok-selection-freeze.json", expected_freeze_sha256=state["context"]["freeze_sha256"],
                                expected_freeze_verifier_sha256=state["verifier_sha"], freeze_verifier_path=state["verifier"], batch_number=number,
                                allow_remote=True, strict_review_path=review[0], expected_strict_review_sha256=review[1],
                                broker_factory=lambda _root: route_support.Broker(route))


def settle(value: Any, campaign: Path, state: dict[str, Any], number: int) -> dict[str, Any]:
    return value.settle_batch(campaign_root=campaign, freeze_root=FREEZE_ROOT, freeze_path=campaign.parent / "grok-selection-freeze.json",
                              expected_freeze_sha256=state["context"]["freeze_sha256"], expected_freeze_verifier_sha256=state["verifier_sha"],
                              freeze_verifier_path=state["verifier"], batch_number=number)


def test_strict_schema_is_exact_root_delta_and_validates_refs_and_bounds() -> None:
    value = subject()
    schema = {"$defs": {"score": {"type": "integer", "minimum": 0, "maximum": 4}}, "type": "object", "additionalProperties": False,
              "properties": {"A": {"type": "object", "additionalProperties": False, "properties": {"score": {"$ref": "#/$defs/score"}}, "required": ["score"]},
                             "B": {"type": "object", "additionalProperties": False, "properties": {"score": {"$ref": "#/$defs/score"}}, "required": ["score"]},
                             "observed_winner": {"enum": ["A", "B", "TIE"]}}, "required": ["A", "B"]}
    strict = value.strict_native_schema(schema)
    assert strict["required"] == ["A", "B", "observed_winner"]
    assert {key: item for key, item in strict.items() if key != "required"} == {key: item for key, item in schema.items() if key != "required"}
    value._validate(strict, {"A": {"score": 1}, "B": {"score": 4}, "observed_winner": "B"})
    with pytest.raises(ValueError, match="required"):
        value._validate(strict, {"A": {"score": 1}, "B": {"score": 4}})
    with pytest.raises(ValueError, match="maximum"):
        value._validate(strict, {"A": {"score": 5}, "B": {"score": 4}, "observed_winner": "B"})
    with pytest.raises(ValueError, match="exclusiveMinimum"):
        value._validate({"type": "number", "minimum": 1, "exclusiveMinimum": True}, 1)


def test_real_launcher_preserves_payload_and_uses_external_strict_schema(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    value = subject(); campaign, queue, _created, route_support, state = create(value, tmp_path, monkeypatch)
    prepared, route = prepare(value, campaign, queue, route_support, state); review = strict_review(value, campaign, 1)
    calls: list[list[str]] = []; synthetic_subprocess(value, monkeypatch, calls)
    outcomes = dispatch(value, campaign, queue, route_support, state, route, 1, review); settled = settle(value, campaign, state, 1)
    assert len(outcomes) == len(calls) == 10 and settled["status"] == "completed"
    batch = campaign / "batches/0001"; projection = json.loads((batch / "strict-schema-projection.json").read_bytes())
    for cell_id in prepared["prepared_cells"]:
        root = batch / "execution" / cell_id
        assert (root / "outbound-payload.json").read_bytes() == value._configured_legacy()[0]._frozen()._resolution(freeze_root=FREEZE_ROOT)["payloads"][cell_id]
        assert Path(projection["actual_commands"][cell_id][projection["actual_commands"][cell_id].index("--output-schema") + 1]) == batch / "strict-native-schema.json"
        assert (root / "launch-intent.json").is_file() and (root / "execution-receipt.json").is_file()
    assert all(command[-1] == "-" for command in calls)


def test_source_schema_review_and_command_drift_fail_before_contact(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    value = subject(); campaign, queue, _created, route_support, state = create(value, tmp_path, monkeypatch)
    _prepared, route = prepare(value, campaign, queue, route_support, state); review = strict_review(value, campaign, 1)
    calls: list[list[str]] = []; synthetic_subprocess(value, monkeypatch, calls)
    batch = campaign / "batches/0001"; projection_path = batch / "strict-schema-projection.json"; projection = json.loads(projection_path.read_bytes())
    projection["actual_commands"][projection["cell_ids"][0]][0] = "forged-codex"; projection["actual_command_sha256s"] = {key: value.sha256(command) for key, command in projection["actual_commands"].items()}; projection_path.write_bytes(value.canonical(projection))
    with pytest.raises(ValueError, match="strict successor independent review|projection"):
        dispatch(value, campaign, queue, route_support, state, route, 1, review)
    assert calls == []


def test_failed_process_records_launch_intent_and_cannot_resend(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    value = subject(); campaign, queue, _created, route_support, state = create(value, tmp_path, monkeypatch)
    _prepared, route = prepare(value, campaign, queue, route_support, state); review = strict_review(value, campaign, 1)
    calls: list[list[str]] = []; synthetic_subprocess(value, monkeypatch, calls, fail=True)
    with pytest.raises(ValueError, match="stopped after a terminal failure"):
        dispatch(value, campaign, queue, route_support, state, route, 1, review)
    assert calls and any((campaign / "batches/0001/execution" / cell / "launch-intent.json").is_file() for cell in json.loads((campaign / "batches/0001/plan.json").read_bytes())["cell_ids"])
    with pytest.raises((ValueError, FileExistsError)):
        dispatch(value, campaign, queue, route_support, state, route, 1, review)


def test_full_129_report_replays_native_admissions_not_settlement_counts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    value = subject(); campaign, queue, _created, route_support, state = create(value, tmp_path, monkeypatch)
    calls: list[list[str]] = []; synthetic_subprocess(value, monkeypatch, calls)
    for number in range(1, 14):
        prepared, route = prepare(value, campaign, queue, route_support, state, number)
        assert len(prepared["prepared_cells"]) == (9 if number == 13 else 10)
        outcomes = dispatch(value, campaign, queue, route_support, state, route, number, strict_review(value, campaign, number))
        assert len(outcomes) == len(prepared["prepared_cells"])
        assert settle(value, campaign, state, number)["status"] == "completed"
    result = value.report(campaign_root=campaign, freeze_root=FREEZE_ROOT, freeze_path=campaign.parent / "grok-selection-freeze.json",
                          expected_freeze_sha256=state["context"]["freeze_sha256"], expected_freeze_verifier_sha256=state["verifier_sha"],
                          freeze_verifier_path=state["verifier"])
    assert len(calls) == len({tuple(command) for command in calls}) == result["measurement_count"] == result["native_admissions"] == 129
    first = campaign / "batches/0001/execution" / json.loads((campaign / "batches/0001/plan.json").read_bytes())["cell_ids"][0] / "raw-codex-final-response.bin"
    first.write_bytes(b"{}")
    with pytest.raises(ValueError, match="final response|receipt binding|strict|required property"):
        value.report(campaign_root=campaign, freeze_root=FREEZE_ROOT, freeze_path=campaign.parent / "grok-selection-freeze.json",
                     expected_freeze_sha256=state["context"]["freeze_sha256"], expected_freeze_verifier_sha256=state["verifier_sha"],
                     freeze_verifier_path=state["verifier"])
